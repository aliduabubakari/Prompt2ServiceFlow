"""Conservative, idempotent public-evidence repairs; no hidden answers."""
from __future__ import annotations

import copy
import json

import compatibility_analysis as analysis

INGESTOR = 'bounded_timeseries_event_ingestor'


def manifests(active, profile, max_bytes=2_000_000):
    candidates = []
    for path in sorted(active.rglob('*.json')):
        try:
            relative = path.relative_to(active).as_posix()
            path = analysis.safe_path(active, relative)
            if not path.is_file() or path.stat().st_size > max_bytes:
                continue
            value = json.loads(path.read_text()); inputs = value.get('inputs') if isinstance(value, dict) else None
            if not isinstance(inputs, dict) or not set(profile['input_keys'].values()).issubset(inputs):
                continue
            if not {'batch_window_start', 'batch_window_end', 'window_size_minutes', 'demand_threshold_pct', 'power_factor_min'}.issubset(value):
                continue
            if all(analysis.safe_path(active, inputs[key]).is_file() for key in profile['input_keys'].values()):
                candidates.append(relative)
        except (ValueError, TypeError, OSError):
            continue
    return candidates


def repair(ir, profile, active, catalog_get):
    """Caller checks structure/dataflow and non-repairable catalog errors first."""
    value = copy.deepcopy(ir); edits, decisions = [], []
    candidates = manifests(active, profile)
    artifacts = {a['artifact_id']: a for a in value['artifacts']}
    existing_ids = set(artifacts)
    for index, binding in enumerate(value['bindings']):
        intent = binding['intent_id']
        if binding['service_id'] == INGESTOR:
            ports = binding['input_bindings']
            if len(ports) == 1 and ports[0]['port'] == 'input_artifacts':
                artifact = artifacts.get(ports[0]['artifact_id'])
                if artifact and not artifact.get('producer') and artifact.get('role') == 'input' and artifact.get('data_type') in ('any', 'json', 'object'):
                    if 'fixture_ref' not in artifact and len(candidates) == 1:
                        position = next(i for i, a in enumerate(value['artifacts']) if a is artifact)
                        reference = 'fixtures/inputs/' + candidates[0]
                        artifact['fixture_ref'] = reference
                        edits.append({'op': 'add', 'path': f'/artifacts/{position}/fixture_ref', 'value': reference,
                                      'rule': 'unique_public_manifest', 'evidence': {'manifest': candidates[0], 'candidate_count': 1}})
                    else:
                        decisions.append({'intent_id': intent, 'rule': 'unique_public_manifest',
                                          'reason': 'existing_reference_preserved' if 'fixture_ref' in artifact else 'manifest_not_unique',
                                          'candidate_count': len(candidates)})
                else:
                    decisions.append({'intent_id': intent, 'rule': 'unique_public_manifest', 'reason': 'input_role_or_type_not_supported'})
            else:
                decisions.append({'intent_id': intent, 'rule': 'unique_public_manifest', 'reason': 'no_unique_existing_input_binding'})
        descriptor, error = catalog_get(binding['service_id'], binding['service_version'])
        if error or not descriptor:
            decisions.append({'intent_id': intent, 'rule': 'required_status', 'reason': 'public_descriptor_unavailable'}); continue
        declaration = next((p for p in descriptor['interface']['outputs'] if p['name'] == 'execution_report'), None)
        if (not declaration or declaration.get('required') is not True or declaration.get('cardinality') != 'one'
                or declaration.get('data_type') != 'status' or any(p['port'] == 'execution_report' for p in binding['output_bindings'])):
            continue
        # Existing status artifacts with a producer but no writer require a
        # different repair rule. Do not choose among them or silently duplicate.
        if any(a.get('producer') == intent and a.get('data_type') == 'status' for a in value['artifacts']):
            decisions.append({'intent_id': intent, 'rule': 'required_status', 'reason': 'existing_status_artifact_requires_review'}); continue
        base = intent + '_v2_execution_report'; identity = base; suffix = 2
        while identity in existing_ids:
            identity = base + '_' + str(suffix); suffix += 1
        existing_ids.add(identity)
        artifact = {'artifact_id': identity, 'name': 'Execution report', 'kind': 'artifact', 'data_type': 'status',
                    'media_type': 'application/json', 'role': 'status', 'producer': intent, 'consumers': [],
                    'sensitivity': 'internal', 'persistence': 'workflow'}
        position = len(value['artifacts']); value['artifacts'].append(artifact)
        port = {'port': 'execution_report', 'artifact_id': identity}
        binding_position = len(binding['output_bindings']); binding['output_bindings'].append(port)
        evidence = {'service_id': binding['service_id'], 'service_version': binding['service_version'],
                    'required_port': 'execution_report', 'type': 'status', 'cardinality': 'one'}
        edits.extend([{'op': 'add', 'path': f'/artifacts/{position}', 'value': artifact, 'rule': 'required_status', 'evidence': evidence},
                      {'op': 'add', 'path': f'/bindings/{index}/output_bindings/{binding_position}', 'value': port,
                       'rule': 'required_status', 'evidence': evidence}])
    return value, edits, decisions
