"""Independent checks on declared primary/audit/status projections."""
from __future__ import annotations

import copy
import json

import bounded_window_oracle as base


def primary(ir):
    publisher = next(b for b in ir['bindings'] if b['service_id'] == base.PUBLISHER)
    artifacts = {a['artifact_id']: a for a in ir['artifacts']}
    data = [o for o in publisher['output_bindings'] if o['port'] == 'output_artifacts']
    if len(data) == 1 and artifacts[data[0]['artifact_id']].get('role') in ('output', 'intermediate'):
        return data[0]['artifact_id']
    choices = [o['artifact_id'] for o in data if artifacts[o['artifact_id']].get('role') == 'output'
               and artifacts[o['artifact_id']].get('data_type') in ('any', 'object', 'json', 'table')]
    if len(choices) != 1:
        raise ValueError('Evaluator cannot identify one primary publication')
    return choices[0]


def check(result, ir, fixtures, profile, scenario, schemas=None):
    view = copy.deepcopy(ir)
    identity = primary(ir)
    publisher = next(b for b in view['bindings'] if b['service_id'] == base.PUBLISHER)
    publisher['output_bindings'].sort(key=lambda o: o['artifact_id'] != identity)
    evaluation = base.check(result, view, fixtures, profile, scenario, schemas)
    evaluation['scope'] = 'paired_v2_interpretation_not_original_g6_assert'
    if scenario in ('conflicting_duplicate', 'unknown_building', 'missing_energy'):
        return evaluation
    checks = evaluation['checks']
    try:
        snapshot = result['_snapshot']
        trace = json.loads(snapshot['logs/bounded_window_trace.json'])
        payload = json.loads(snapshot['artifacts/' + identity + '.json'])
        audit = json.loads(snapshot[payload['published_files']['audit']])
        for binding in ir['bindings']:
            for output in binding['output_bindings']:
                value = json.loads(snapshot['artifacts/' + output['artifact_id'] + '.json'])
                if output['port'] == 'execution_report':
                    status = (value.get('success') is True and value.get('errors') == []
                              and value.get('service_id') == binding['service_id'])
                    checks.append({'check': 'bound_status:' + output['artifact_id'], 'pass': status})
                elif binding['service_id'] == base.PUBLISHER and output['artifact_id'] != identity:
                    checks.append({'check': 'bound_audit_matches_actual_publication:' + output['artifact_id'], 'pass': value == audit})
        checks.append({'check': 'profile_override_trace_retains_original_labels', 'pass':
            {x['intent_id']: x['original_label'] for x in trace['profile_overrides']} ==
            {b['intent_id']: b['parameter_bindings']['operation_profile'] for b in ir['bindings']}})
    except Exception as exc:
        checks.append({'check': 'projection_evaluation_error', 'pass': False, 'error': f'{type(exc).__name__}: {exc}'})
    evaluation['pass'] = bool(checks) and all(c['pass'] for c in checks)
    return evaluation
