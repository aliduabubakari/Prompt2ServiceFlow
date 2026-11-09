"""Separate exhaustive-window/decimal oracle for the clarified public profile.

Does not call executor kernels, load gold assertions, or read native reference
programs. It checks actual task inputs against final bound outputs/files.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path

PUBLISHER = 'timeseries_output_bundle_publisher'


def source_path(root, relative):
    path = Path(relative)
    result = (root / path).resolve()
    if path.is_absolute() or '..' in path.parts or not result.is_relative_to(root.resolve()):
        raise ValueError('Expected public input path escapes fixture root')
    return result


def time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Missing timezone')
    return result.astimezone(timezone.utc)


def z(value):
    return value.isoformat().replace('+00:00', 'Z')


def expected(fixtures, profile):
    config = json.loads((fixtures / 'fixture.json').read_text())
    fields = profile['fields']
    paths = config['inputs']
    records = [json.loads(line) for line in source_path(fixtures, paths[profile['input_keys']['records']]).read_text().splitlines() if line.strip()]
    with source_path(fixtures, paths[profile['input_keys']['registry']]).open(newline='') as handle:
        registry = list(csv.DictReader(handle))
    capacities = {r[fields['group']]: Decimal(r[fields['capacity']]) for r in registry}
    unique = {}
    for row in records:
        projected = (row[fields['entity']], row[fields['group']], time(row[fields['time']]),
                     *[Decimal(str(row[fields[k]])) for k in ('energy', 'demand', 'quality')])
        key = projected[0], projected[2]
        if key in unique and projected != unique[key]:
            raise ValueError('Oracle requires a consistent positive input')
        unique[key] = projected
    start, end = time(config['batch_window_start']), time(config['batch_window_end'])
    width = timedelta(minutes=config['window_size_minutes'])
    metrics = []
    left = start
    while left < end:
        right = min(left + width, end)
        for group in sorted(capacities):
            selected = [r for r in unique.values() if r[1] == group and left <= r[2] < right]
            if not selected:
                continue
            sums = [sum(r[4] for r in selected if r[2] == instant) for instant in {r[2] for r in selected}]
            peak = max(sums)
            quality = sum(r[5] for r in selected) / len(selected)
            pct = peak * 100 / capacities[group]
            metrics.append({'group_id': group, 'window_start': z(left), 'window_end': z(right), 'record_count': len(selected),
                'energy_kwh_sum': float(sum(r[3] for r in selected)), 'peak_demand_kw': float(peak),
                'mean_power_factor': float(quality), 'demand_pct': float(pct),
                'high_demand': pct >= Decimal(str(config['demand_threshold_pct'])),
                'low_power_factor': quality < Decimal(str(config['power_factor_min']))})
        left = right
    inside = sum(start <= r[2] < end for r in unique.values())
    counts = {'raw_rows': len(records), 'unique_rows': len(unique), 'duplicates_removed': len(records) - len(unique),
              'in_range_rows': inside, 'out_of_range_rows': len(unique) - inside, 'windows': len(metrics)}
    return metrics, counts


def equivalent(actual, expected_rows):
    def index(rows):
        result = {}
        for row in rows:
            key = row['group_id'], row['window_start'], row['window_end']
            if key in result:
                return None
            result[key] = row
        return result
    a, b = index(actual), index(expected_rows)
    if a is None or b is None or set(a) != set(b):
        return False
    for key in b:
        for field, value in b[key].items():
            if isinstance(value, bool):
                if a[key].get(field) is not value:
                    return False
            elif isinstance(value, (int, float)):
                candidate = a[key].get(field)
                if isinstance(candidate, bool) or not isinstance(candidate, (int, float)):
                    return False
                from math import isclose
                if not isclose(candidate, value, rel_tol=1e-9, abs_tol=1e-9):
                    return False
            elif a[key].get(field) != value:
                return False
    return True


def check(result, ir, fixtures, profile, scenario, schemas=None):
    checks = []
    def add(name, passed):
        checks.append({'check': name, 'pass': bool(passed)})
    snapshot = result['_snapshot']
    negative_stages = {'conflicting_duplicate': 'timeseries_record_sort_deduplicator',
                       'unknown_building': 'bounded_window_checkpoint_validator',
                       'missing_energy': 'bounded_window_checkpoint_validator'}
    try:
        trace = json.loads(snapshot['logs/bounded_window_trace.json'])
        bindings = {b['service_id']: b for b in ir['bindings']}
        publisher = bindings[PUBLISHER]
        final_id = next(o['artifact_id'] for o in publisher['output_bindings'] if o['port'] == 'output_artifacts')
        final_path = 'artifacts/' + final_id + '.json'
        if scenario in negative_stages:
            failed = bindings[negative_stages[scenario]]['intent_id']
            add('expected_stage_rejects', trace['states'].get(failed) == 'failed')
            add('publisher_not_executed', trace['states'].get(publisher['intent_id']) == 'skipped' and final_path not in snapshot)
            marker = {'conflicting_duplicate': 'Conflicting duplicate', 'unknown_building': 'Unknown registry group', 'missing_energy': 'KeyError'}[scenario]
            add('specific_failure_reason', any(e['intent_id'] == failed and marker in e.get('error', '') for e in trace['events']))
            if scenario == 'missing_energy':
                add('missing_declared_energy_field', any(e['intent_id'] == failed and profile['fields']['energy'] in e.get('error', '') for e in trace['events']))
            return {'pass': all(c['pass'] for c in checks), 'checks': checks, 'scope': 'clarified_v2_profile'}
        add('all_six_steps_executed', len(trace['states']) == 6 and all(v == 'executed' for v in trace['states'].values())
            and trace['workflow_status'] == 'completed' and not result['_errors'])
        payload = json.loads(snapshot[final_path])
        rows, counts = expected(fixtures, profile)
        add('computed_metrics_equal_public_oracle', equivalent(payload['metrics'], rows))
        add('input_duplicate_boundary_window_counts', payload['counts'] == counts)
        csv_path, audit_path = payload['published_files']['csv'], payload['published_files']['audit']
        if any(not isinstance(p, str) or not p.startswith('published/') or '..' in p.split('/') for p in (csv_path, audit_path)):
            raise ValueError('Unsafe published path')
        raw = snapshot[csv_path]
        csv_rows = list(csv.DictReader(io.StringIO(raw.decode())))
        parsed = []
        for row in csv_rows:
            for field in ('record_count',):
                row[field] = int(row[field])
            for field in ('energy_kwh_sum', 'peak_demand_kw', 'mean_power_factor', 'demand_pct'):
                row[field] = float(row[field])
            for field in ('high_demand', 'low_power_factor'):
                if row[field] not in ('True', 'False'):
                    raise ValueError('Non-Boolean CSV alert flag')
                row[field] = row[field] == 'True'
            parsed.append(row)
        add('published_csv_values_equal_public_oracle', equivalent(parsed, rows))
        audit = json.loads(snapshot[audit_path])
        add('audit_counts_and_csv_integrity', audit['counts'] == counts and audit['csv_sha256'] == hashlib.sha256(raw).hexdigest())
        add('profile_integrity', audit['profile_sha256'] == hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest())
        config = json.loads((fixtures / 'fixture.json').read_text())
        expected_source_hashes = {}
        for name in ('records', 'registry'):
            filename = config['inputs'][profile['input_keys'][name]]
            expected_source_hashes[name] = hashlib.sha256(source_path(fixtures, filename).read_bytes()).hexdigest()
        add('public_source_integrity', audit['source_sha256'] == expected_source_hashes)
        if schemas:
            from jsonschema import Draft202012Validator
            for b in ir['bindings']:
                for output in b['output_bindings']:
                    schema = schemas.get(output['artifact_id'])
                    if schema:
                        Draft202012Validator(schema).validate(json.loads(snapshot['artifacts/' + output['artifact_id'] + '.json']))
            add('public_artifact_schemas', True)
    except Exception as exc:
        checks.append({'check': 'evaluation_error', 'pass': False, 'error': f'{type(exc).__name__}: {exc}'})
    return {'pass': bool(checks) and all(c['pass'] for c in checks), 'checks': checks, 'scope': 'clarified_v2_profile'}
