"""Parameterized finite-window kernels; no pipeline/model-name switches.

Semantics come from an explicit versioned public profile and bound inputs.
Only standard-library dependencies are needed in the network-disabled sandbox.
"""
from __future__ import annotations

from collections import defaultdict
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import io
import json
import math
from pathlib import Path


class Unsupported(ValueError):
    pass


def verify_profile(profile):
    required = {'window_precedence': 'fixture_window_size_minutes', 'bounds': 'start_inclusive_end_exclusive',
        'energy': 'sum_interval_energy_not_cumulative', 'duplicate_key': ['entity', 'time'],
        'duplicates': 'collapse_identical_reject_conflicts', 'grouping': 'group_and_window',
        'peak_demand': 'max_of_sum_per_timestamp', 'quality': 'arithmetic_mean', 'empty_windows': 'omit',
        'demand_alert': 'greater_than_or_equal', 'quality_alert': 'strictly_less', 'unknown_registry_group': 'reject'}
    if profile.get('rules') != required:
        raise Unsupported('Profile semantics changed; a new implementation/version is required')


def contained(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('A contained relative path is required')
    result = (root / path).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError('Path escapes its declared root')
    return result


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Timestamp must be an explicit timezone-aware string')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Naive timestamps are not supported')
    return result.astimezone(timezone.utc)


def stamp(value):
    return value.isoformat().replace('+00:00', 'Z')


def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError('Invalid numeric field: ' + name)
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Non-finite numeric field: ' + name)
    return value


def ingest(bundle, fixtures, profile):
    paths = bundle.get('inputs', {})
    records_path = contained(fixtures, paths[profile['input_keys']['records']])
    registry_path = contained(fixtures, paths[profile['input_keys']['registry']])
    records = [json.loads(line) for line in records_path.read_text().splitlines() if line.strip()]
    with registry_path.open(newline='') as handle:
        registry = list(csv.DictReader(handle))
    return {'config': bundle, 'records': records, 'registry': registry,
            'source_sha256': {'records': hashlib.sha256(records_path.read_bytes()).hexdigest(),
                              'registry': hashlib.sha256(registry_path.read_bytes()).hexdigest()},
            'counts': {'raw_rows': len(records)}}


def validate(payload, profile):
    fields, config = profile['fields'], payload['config']
    start, end = timestamp(config['batch_window_start']), timestamp(config['batch_window_end'])
    minutes = config['window_size_minutes']
    if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes <= 0 or end <= start:
        raise ValueError('Positive integer windows and increasing batch bounds required')
    if not 0 <= number(config['demand_threshold_pct'], 'threshold') <= 100:
        raise ValueError('Demand threshold must be within 0..100')
    if not 0 <= number(config['power_factor_min'], 'minimum quality') <= 1:
        raise ValueError('Quality minimum must be within 0..1')
    groups = {}
    for row in payload['registry']:
        identity = row[fields['group']]
        if not isinstance(identity, str) or not identity or identity in groups:
            raise ValueError('Registry identifiers must be unique and non-empty')
        capacity = number(row[fields['capacity']], 'capacity')
        if capacity <= 0:
            raise ValueError('Registry capacity must be positive')
        groups[identity] = capacity
    records = []
    for raw in payload['records']:
        row = {key: raw[fields[key]] for key in ('entity', 'group', 'time', 'energy', 'demand', 'quality')}
        if not all(isinstance(row[k], str) and row[k] for k in ('entity', 'group')):
            raise ValueError('Entity/group identifiers are required')
        if row['group'] not in groups:
            raise ValueError('Unknown registry group')
        row['time'] = stamp(timestamp(row['time']))
        for key in ('energy', 'demand', 'quality'):
            row[key] = number(row[key], key)
        if row['energy'] < 0 or row['demand'] < 0 or not 0 <= row['quality'] <= 1:
            raise ValueError('Measurements outside declared range')
        records.append(row)
    return {**payload, 'records': records, 'capacities': groups}


def deduplicate(payload, profile):
    unique = {}
    for row in payload['records']:
        key = row['entity'], row['time']
        if key in unique and unique[key] != row:
            raise ValueError('Conflicting duplicate')
        unique[key] = row
    rows = sorted(unique.values(), key=lambda r: (r['time'], r['entity']))
    return {**payload, 'records': rows, 'counts': {**payload['counts'], 'unique_rows': len(rows),
             'duplicates_removed': len(payload['records']) - len(rows)}}


def window(payload, profile):
    config = payload['config']
    start, end = timestamp(config['batch_window_start']), timestamp(config['batch_window_end'])
    width = timedelta(minutes=config['window_size_minutes'])
    windows, outside = defaultdict(list), 0
    for row in payload['records']:
        time = timestamp(row['time'])
        if not start <= time < end:
            outside += 1
            continue
        left = start + ((time - start) // width) * width
        windows[row['group'], stamp(left), stamp(min(left + width, end))].append(row)
    groups = [{'group_id': key[0], 'window_start': key[1], 'window_end': key[2], 'records': rows}
              for key, rows in sorted(windows.items())]
    return {**payload, 'windows': groups, 'counts': {**payload['counts'],
             'out_of_range_rows': outside, 'in_range_rows': len(payload['records']) - outside, 'windows': len(groups)}}


def aggregate(payload, profile):
    output = []
    for group in payload['windows']:
        rows = group['records']
        coincident = defaultdict(list)
        for row in rows:
            coincident[row['time']].append(row['demand'])
        peak = max(sum(Decimal(str(v)) for v in values) for values in coincident.values())
        quality = sum(Decimal(str(r['quality'])) for r in rows) / len(rows)
        pct = peak / Decimal(str(payload['capacities'][group['group_id']])) * 100
        output.append({'group_id': group['group_id'], 'window_start': group['window_start'], 'window_end': group['window_end'],
                       'record_count': len(rows), 'energy_kwh_sum': math.fsum(r['energy'] for r in rows),
                       'peak_demand_kw': float(peak), 'mean_power_factor': float(quality), 'demand_pct': float(pct),
                       'high_demand': pct >= Decimal(str(payload['config']['demand_threshold_pct'])),
                       'low_power_factor': quality < Decimal(str(payload['config']['power_factor_min']))})
    return {**payload, 'metrics': output}


def publish(payload, profile, workspace, intent):
    root = 'published/' + intent
    csv_name, audit_name = root + '/window_metrics.csv', root + '/audit_manifest.json'
    columns = ['group_id', 'window_start', 'window_end', 'record_count', 'energy_kwh_sum',
               'peak_demand_kw', 'mean_power_factor', 'demand_pct', 'high_demand', 'low_power_factor']
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
    writer.writeheader()
    writer.writerows(payload['metrics'])
    encoded = stream.getvalue().encode()
    audit = {'counts': payload['counts'], 'source_sha256': payload['source_sha256'],
             'profile_sha256': hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest(),
             'csv_sha256': hashlib.sha256(encoded).hexdigest()}
    for name, content in [(csv_name, encoded), (audit_name, (json.dumps(audit, indent=2) + '\n').encode())]:
        path = contained(workspace, name)
        if path.exists():
            raise ValueError('Publisher would overwrite existing output')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return {**payload, 'published_files': {'csv': csv_name, 'audit': audit_name}}
