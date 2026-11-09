"""Public, parameterized relational-join/routing kernels; no pipeline switches."""
from __future__ import annotations

import copy
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import math
from pathlib import Path


class Unsupported(ValueError): pass


RULES = {'join': 'many_primary_to_unique_lookup_exact_key', 'missing_lookup': 'reject',
    'duplicate_record_or_lookup_key': 'reject', 'label_normalization': 'strip_casefold',
    'identity_normalization': 'none', 'lookup_prefix': 'profile_',
    'routing_score': 'priority_weight_times_tier_multiplier', 'score_boundary': 'greater_than_or_equal',
    'escalation': 'immediate_category_or_score_boundary_or_high_churn_with_priority_weight_at_least_policy_threshold',
    'output_order': 'record_id_lexicographic', 'freshness': 'not_claimed_no_logical_clock_contract'}


def verify_profile(p):
    if (set(p) != {'profile_version', 'inputs', 'fields', 'rules'} or p['profile_version'] != 'relational-routing-1'
            or set(p['inputs']) != {'primary', 'secondary', 'reference'} or len(set(p['inputs'].values())) != 3
            or p['rules'] != RULES or set(p['fields']) != {'record_id', 'join_key', 'priority', 'category', 'tier', 'churn', 'numeric_lookup_fields'}):
        raise Unsupported('Unregistered relational profile or rule')
    if not all(isinstance(v, str) and v for v in p['inputs'].values()): raise Unsupported('Input roles must be explicit')
    fields = p['fields']
    if not all(isinstance(fields[k], str) and fields[k] for k in fields if k != 'numeric_lookup_fields'):
        raise Unsupported('Field roles must be explicit')
    if (not isinstance(fields['numeric_lookup_fields'], list)
            or not all(isinstance(v, str) and v for v in fields['numeric_lookup_fields'])
            or len(set(fields['numeric_lookup_fields'])) != len(fields['numeric_lookup_fields'])):
        raise Unsupported('Numeric lookup fields must be explicit and unique')


def digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def contained(root, relative):
    path = Path(relative)
    resolved = (Path(root) / path).resolve()
    if path.is_absolute() or '..' in path.parts or not path.parts or not resolved.is_relative_to(Path(root).resolve()):
        raise ValueError('Input/output path escapes its root')
    return resolved


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value: raise ValueError('Duplicate JSON object key')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON number')))


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('Expected finite numeric value')
    try: result = Decimal(str(value))
    except InvalidOperation as exc: raise ValueError('Expected finite numeric value') from exc
    if not result.is_finite(): raise ValueError('Expected finite numeric value')
    return result


def label(value):
    if not isinstance(value, str) or not value.strip(): raise ValueError('Expected nonempty label')
    return value.strip().casefold()


def identity(value):
    if not isinstance(value, str) or not value.strip(): raise ValueError('Missing identity/join key')
    return value


def finite_float(value):
    result = float(number(value))
    if not math.isfinite(result): raise ValueError('Numeric output exceeds finite JSON range')
    return result


def ingest(manifest, fixtures, profile, role):
    config_key = profile['inputs'][role]
    relative = manifest['inputs'][config_key]
    path = contained(fixtures, relative)
    raw = path.read_bytes()
    if role == 'secondary':
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8')))
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError('Missing or duplicate CSV header')
        value = list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in value): raise ValueError('Ragged CSV row')
    else: value = strict_json(raw.decode('utf-8'))
    if (role in ('primary', 'secondary') and (not isinstance(value, list) or not all(isinstance(row, dict) for row in value))) or (role == 'reference' and not isinstance(value, dict)):
        raise ValueError('Input role has wrong public shape')
    return {'sources': {role: value}, 'source_sha256': {role: hashlib.sha256(raw).hexdigest()},
            'manifest_sha256': digest(manifest)}


def policy_view(policy):
    required = {'priority_weights', 'tier_multipliers', 'escalation_threshold', 'churn_high_priority_threshold', 'categories_requiring_immediate'}
    if not required.issubset(policy): raise ValueError('Missing policy field')
    maps = {}
    for name in ('priority_weights', 'tier_multipliers'):
        if not isinstance(policy[name], dict) or not policy[name]: raise ValueError('Empty policy map')
        converted = {}
        for key, value in policy[name].items():
            key = label(key)
            if key in converted: raise ValueError('Ambiguous normalized policy label')
            converted[key] = number(value)
            if converted[key] <= 0: raise ValueError('Policy weights must be positive')
        maps[name] = converted
    threshold = number(policy['escalation_threshold'])
    if threshold < 0: raise ValueError('Negative escalation threshold')
    churn_threshold = label(policy['churn_high_priority_threshold'])
    if churn_threshold not in maps['priority_weights']: raise ValueError('Unknown churn priority threshold')
    categories = policy['categories_requiring_immediate']
    if not isinstance(categories, list): raise ValueError('Immediate categories must be a list')
    return {**maps, 'threshold': threshold, 'churn_min_weight': maps['priority_weights'][churn_threshold],
            'immediate_categories': {label(v) for v in categories}}


def validate(bundles, profile):
    sources, hashes, manifests = {}, {}, set()
    for bundle in bundles:
        manifests.add(bundle['manifest_sha256'])
        for role, rows in bundle['sources'].items():
            if role in sources: raise ValueError('Duplicate source role in fan-in')
            sources[role] = rows; hashes[role] = bundle['source_sha256'][role]
    if set(sources) != {'primary', 'secondary', 'reference'} or len(manifests) != 1:
        raise ValueError('Three distinct sources from one public manifest required')
    f, policy = profile['fields'], policy_view(sources['reference'])
    keys = set()
    for row in sources['secondary']:
        if any(not isinstance(v, (str, int, float, bool, type(None))) or isinstance(v, float) and not math.isfinite(v) for v in row.values()):
            raise Unsupported('Flat finite scalar records required')
        key = identity(row.get(f['join_key']))
        if key in keys: raise ValueError('Duplicate lookup key')
        keys.add(key)
        if label(row[f['tier']]) not in policy['tier_multipliers']: raise ValueError('Unknown account tier')
        label(row[f['churn']])
        for field in f['numeric_lookup_fields']: number(row[field])
    records = set()
    for row in sources['primary']:
        if any(not isinstance(v, (str, int, float, bool, type(None))) or isinstance(v, float) and not math.isfinite(v) for v in row.values()):
            raise Unsupported('Flat finite scalar records required')
        key, record = identity(row.get(f['join_key'])), identity(row.get(f['record_id']))
        if record in records: raise ValueError('Duplicate primary record identity')
        records.add(record)
        if key not in keys: raise ValueError('Unmatched join key')
        if label(row[f['priority']]) not in policy['priority_weights']: raise ValueError('Unknown priority')
        label(row[f['category']])
    return {'sources': sources, 'source_sha256': hashes, 'manifest_sha256': next(iter(manifests))}


def normalize(bundle, profile):
    out = copy.deepcopy(bundle); f = profile['fields']
    for row in out['sources']['primary']:
        for field in (f['priority'], f['category']): row[field] = label(row[field])
    for row in out['sources']['secondary']:
        for field in (f['tier'], f['churn']): row[field] = label(row[field])
        for field in f['numeric_lookup_fields']: row[field] = finite_float(row[field])
    return out


def reconcile(bundle, profile):
    f = profile['fields']; sources = bundle['sources']; p = policy_view(sources['reference'])
    lookup = {row[f['join_key']]: row for row in sources['secondary']}
    records = []
    reserved = {'priority_weight', 'tier_multiplier', 'routing_score', 'immediate_category',
                'score_threshold_reached', 'churn_priority_trigger', 'escalation_required'}
    for primary in sources['primary']:
        secondary = lookup[primary[f['join_key']]]
        extra = {'profile_' + k: v for k, v in secondary.items() if k != f['join_key']}
        if set(primary) & (set(extra) | reserved) or set(extra) & reserved:
            raise ValueError('Output column collision')
        weight = p['priority_weights'][primary[f['priority']]]
        multiplier = p['tier_multipliers'][secondary[f['tier']]]
        score = weight * multiplier
        immediate = primary[f['category']] in p['immediate_categories']
        boundary = score >= p['threshold']
        churn = secondary[f['churn']] == 'high' and weight >= p['churn_min_weight']
        records.append({**primary, **extra, 'priority_weight': finite_float(weight), 'tier_multiplier': finite_float(multiplier),
                        'routing_score': finite_float(score), 'immediate_category': immediate, 'score_threshold_reached': boundary,
                        'churn_priority_trigger': churn, 'escalation_required': immediate or boundary or churn})
    records.sort(key=lambda r: r[f['record_id']])
    return {'records': records, 'counts': {'primary_rows': len(sources['primary']), 'secondary_rows': len(sources['secondary']),
            'published_rows': len(records), 'escalated_rows': sum(r['escalation_required'] for r in records)},
            'source_sha256': bundle['source_sha256'], 'manifest_sha256': bundle['manifest_sha256']}


def publish(bundle, profile, workspace, intent):
    target = contained(workspace, 'published/' + intent)
    if target.exists(): raise ValueError('Publication overwrite')
    target.mkdir(parents=True)
    fields = sorted({key for row in bundle['records'] for key in row}) or [profile['fields']['record_id']]
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n'); writer.writeheader(); writer.writerows(bundle['records'])
    raw = stream.getvalue().encode()
    (target / 'records.csv').write_bytes(raw)
    audit = {'counts': bundle['counts'], 'source_sha256': bundle['source_sha256'],
             'manifest_sha256': bundle['manifest_sha256'], 'profile_sha256': digest(profile),
             'csv_sha256': hashlib.sha256(raw).hexdigest()}
    (target / 'audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    return {**bundle, 'published_files': {'csv': (target / 'records.csv').relative_to(workspace).as_posix(),
                                         'audit': (target / 'audit.json').relative_to(workspace).as_posix()}}
