"""Independent relational oracle: direct joins and Fraction arithmetic.

Imports neither runtime kernels nor native reference programs/private v1 tests.
"""
from __future__ import annotations

import copy
import csv
from fractions import Fraction
import hashlib
import io
import json
import math
from pathlib import Path

PUBLISHER = 'api_table_output_bundle_publisher'


def sha(value): return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def path_at(root, name):
    path = Path(name)
    resolved = (root / path).resolve()
    if path.is_absolute() or '..' in path.parts or not resolved.is_relative_to(root.resolve()): raise ValueError('Unsafe oracle source path')
    return resolved


def expected(fixtures, profile):
    manifest = json.loads((fixtures / 'fixture.json').read_text())
    paths = {role: path_at(fixtures, manifest['inputs'][key]) for role, key in profile['inputs'].items()}
    primary = json.loads(paths['primary'].read_text())
    with paths['secondary'].open(newline='') as handle: lookup_rows = list(csv.DictReader(handle))
    policy = json.loads(paths['reference'].read_text())
    f = profile['fields']
    normalized = lambda s: s.strip().casefold()
    weights = {normalized(k): Fraction(str(v)) for k, v in policy['priority_weights'].items()}
    tiers = {normalized(k): Fraction(str(v)) for k, v in policy['tier_multipliers'].items()}
    instant = {normalized(k) for k in policy['categories_requiring_immediate']}
    threshold = Fraction(str(policy['escalation_threshold']))
    minimum = weights[normalized(policy['churn_high_priority_threshold'])]
    output = []
    # Exhaustive equality matching rather than the implementation's lookup map.
    for ticket in primary:
        matches = [r for r in lookup_rows if r[f['join_key']] == ticket[f['join_key']]]
        if len(matches) != 1: raise ValueError('Positive oracle requires unique complete join')
        customer = matches[0]
        record = dict(ticket)
        record[f['priority']], record[f['category']] = normalized(ticket[f['priority']]), normalized(ticket[f['category']])
        for name, value in customer.items():
            if name == f['join_key']: continue
            if name in (f['tier'], f['churn']): value = normalized(value)
            if name in f['numeric_lookup_fields']: value = float(Fraction(str(value)))
            record['profile_' + name] = value
        weight, multiplier = weights[record[f['priority']]], tiers[normalized(customer[f['tier']])]
        score = weight * multiplier
        immediate = record[f['category']] in instant
        boundary = score >= threshold
        churn = normalized(customer[f['churn']]) == 'high' and weight >= minimum
        record.update(priority_weight=float(weight), tier_multiplier=float(multiplier), routing_score=float(score),
                      immediate_category=immediate, score_threshold_reached=boundary, churn_priority_trigger=churn,
                      escalation_required=bool(immediate or boundary or churn))
        output.append(record)
    output.sort(key=lambda r: r[f['record_id']])
    return output, {'primary_rows': len(primary), 'secondary_rows': len(lookup_rows), 'published_rows': len(output),
                    'escalated_rows': sum(r['escalation_required'] for r in output)}, paths, manifest


def equivalent(actual, expected_value):
    if isinstance(expected_value, bool): return type(actual) is bool and actual is expected_value
    if isinstance(expected_value, (int, float)):
        return (isinstance(actual, (int, float)) and not isinstance(actual, bool) and math.isfinite(actual)
                and Fraction(str(actual)) == Fraction(str(expected_value)))
    if isinstance(expected_value, dict):
        return isinstance(actual, dict) and set(actual) == set(expected_value) and all(equivalent(actual[k], v) for k, v in expected_value.items())
    if isinstance(expected_value, list):
        return isinstance(actual, list) and len(actual) == len(expected_value) and all(equivalent(a, e) for a, e in zip(actual, expected_value))
    return type(actual) is type(expected_value) and actual == expected_value


def primary(ir):
    b = next(b for b in ir['bindings'] if b['service_id'] == PUBLISHER)
    artifacts = {a['artifact_id']: a for a in ir['artifacts']}
    values = [o['artifact_id'] for o in b['output_bindings'] if o['port'] == 'output_artifacts']
    if len(values) == 1: return values[0]
    chosen = [identity for identity in values if artifacts[identity]['role'] == 'output']
    if len(chosen) != 1: raise ValueError('Ambiguous primary output')
    return chosen[0]


def check(result, ir, fixtures, profile, negative_scenarios):
    checks = []
    add = lambda name, passed: checks.append({'check': name, 'pass': bool(passed)})
    scenario = result['scenario']; snapshot = result['_snapshot']
    try:
        receipt = json.loads(snapshot['logs/fusion_backend_receipt.json'])
        add('exact_real_backend_receipt', receipt.get('backend_id') == 'p2sf.semantic.relational/1'
            and receipt.get('ir_sha256') == sha(ir) and receipt.get('profile_sha256') == sha(profile)
            and receipt.get('strict_labels_verified') is True and receipt.get('mock_fallback') is False and receipt.get('label_replacements') == [])
        trace = json.loads(snapshot['logs/fusion_trace.json'])
        identity = primary(ir)
        publisher = next(b for b in ir['bindings'] if b['service_id'] == PUBLISHER)
        if scenario in negative_scenarios:
            stage = next(b for b in ir['bindings'] if b['service_id'] == 'api_table_multi_source_contract_validator')['intent_id']
            add('expected_validator_rejects', trace['states'].get(stage) == 'failed')
            add('specific_failure_reason', any(e['intent_id'] == stage and negative_scenarios[scenario] in e.get('error', '') for e in trace['events']))
            add('no_publication_after_rejection', trace['states'].get(publisher['intent_id']) == 'skipped'
                and 'artifacts/' + identity + '.json' not in snapshot and not any(name.startswith('published/') for name in snapshot))
        else:
            add('all_seven_stages_executed', len(trace['states']) == 7 and all(s == 'executed' for s in trace['states'].values())
                and trace['workflow_status'] == 'completed' and receipt['workflow_status'] == 'completed' and not result['_errors'])
            payload = json.loads(snapshot['artifacts/' + identity + '.json'])
            records, counts, sources, manifest = expected(fixtures, profile)
            add('joined_records_and_routing_from_public_sources', equivalent(payload['records'], records))
            add('independent_row_and_escalation_counts', equivalent(payload['counts'], counts))
            paths = payload['published_files']
            for path in paths.values():
                if not isinstance(path, str) or not path.startswith('published/') or '..' in Path(path).parts: raise ValueError('Unsafe published path')
            csv_bytes = snapshot[paths['csv']]
            reader = csv.DictReader(io.StringIO(csv_bytes.decode()))
            csv_rows = list(reader)
            columns = sorted({key for row in records for key in row}) or [profile['fields']['record_id']]
            csv_ok = (len(csv_rows) == len(records) and reader.fieldnames is not None
                      and len(reader.fieldnames) == len(set(reader.fieldnames)) and set(reader.fieldnames) == set(columns))
            for actual, row in zip(csv_rows, records):
                csv_ok &= set(actual) == set(row)
                for key, value in row.items():
                    cell = actual.get(key)
                    if isinstance(value, bool): csv_ok &= cell == str(value)
                    elif isinstance(value, (int, float)): csv_ok &= cell is not None and Fraction(cell) == Fraction(str(value))
                    elif value is None: csv_ok &= cell == ''
                    else: csv_ok &= cell == value
            add('published_csv_values', csv_ok)
            audit = json.loads(snapshot[paths['audit']])
            hashes = {role: hashlib.sha256(path.read_bytes()).hexdigest() for role, path in sources.items()}
            add('actual_source_manifest_profile_and_csv_hashes', audit['source_sha256'] == hashes and audit['manifest_sha256'] == sha(manifest)
                and audit['profile_sha256'] == sha(profile) and audit['csv_sha256'] == hashlib.sha256(csv_bytes).hexdigest() and equivalent(audit['counts'], counts))
            for binding in ir['bindings']:
                for bound in binding['output_bindings']:
                    value = json.loads(snapshot['artifacts/' + bound['artifact_id'] + '.json'])
                    if bound['port'] == 'execution_report':
                        add('bound_execution_report:' + bound['artifact_id'], value.get('success') is True and value.get('errors') == [] and value.get('service_id') == binding['service_id'])
                    elif binding['service_id'] == PUBLISHER and bound['artifact_id'] != identity:
                        add('bound_audit_projection', value == audit)
    except Exception as exc:
        checks.append({'check': 'missing_or_invalid_business_output', 'pass': False, 'error': type(exc).__name__ + ': ' + str(exc)})
    return {'scenario': scenario, 'kind': 'expected_input_rejection' if scenario in negative_scenarios else 'positive_business_output',
            'pass': bool(checks) and all(c['pass'] for c in checks), 'checks': checks,
            'scope': 'new_explicit_relational_v2_contract_not_original_g6'}


def mutate(result, ir, profile, defect):
    result = copy.deepcopy(result); snapshot = result['_snapshot']
    bound = 'artifacts/' + primary(ir) + '.json'; payload = json.loads(snapshot[bound])
    if defect == 'empty_records': payload['records'] = []
    elif defect == 'wrong_join': payload['records'][0]['profile_' + profile['fields']['tier']] = 'incorrect_join'
    elif defect == 'wrong_score': payload['records'][0]['routing_score'] += 1
    elif defect == 'wrong_escalation': payload['records'][0]['escalation_required'] = not payload['records'][0]['escalation_required']
    else: raise ValueError('Unknown registered mutant')
    payload['counts']['published_rows'] = len(payload['records'])
    payload['counts']['escalated_rows'] = sum(r['escalation_required'] for r in payload['records'])
    csv_path, audit_path = payload['published_files']['csv'], payload['published_files']['audit']
    fields = next(csv.reader(io.StringIO(snapshot[csv_path].decode())))
    stream = io.StringIO(newline=''); writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
    writer.writeheader(); writer.writerows(payload['records']); raw = stream.getvalue().encode()
    snapshot[csv_path] = raw
    audit = json.loads(snapshot[audit_path]); audit['csv_sha256'] = hashlib.sha256(raw).hexdigest(); audit['counts'] = payload['counts']
    snapshot[audit_path] = json.dumps(audit).encode(); snapshot[bound] = json.dumps(payload).encode()
    b = next(b for b in ir['bindings'] if b['service_id'] == PUBLISHER)
    for o in b['output_bindings']:
        if o['port'] == 'output_artifacts' and o['artifact_id'] != primary(ir): snapshot['artifacts/' + o['artifact_id'] + '.json'] = json.dumps(audit).encode()
    return result
