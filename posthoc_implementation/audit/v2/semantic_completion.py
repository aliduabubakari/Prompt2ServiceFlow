"""Typed auxiliary-output completion followed by declared IR assembly.

No pipeline/model/artifact-name switches, reference IR, private answers, or
numerical repair. A projection is allowed only when its real implementation
and exact public service/port contract are registered.
"""
from __future__ import annotations

import copy

import binding_assembly


def validate_contract(contract):
    rule = {'service_id': 'timeseries_output_bundle_publisher', 'service_version': '1.0.0',
            'operation_profile': 'publish_outputs', 'port': 'output_artifacts',
            'artifact_role': 'report', 'artifact_data_types': ['json', 'object'],
            'projection': 'publication_audit_manifest', 'maximum_auxiliary_reports': 1,
            'require_declared_intent_output': True, 'require_no_consumers': True}
    if (contract.get('projection_contract_version') != 'p2sf.public-output-projections/1'
            or contract.get('profile_version') != 'bounded-window-1' or contract.get('rules') != [rule]):
        raise ValueError('No verified runtime implementation for this output-projection contract')


def complete(ir, catalog_get, contract, assembly_policy):
    validate_contract(contract)
    original = copy.deepcopy(ir)
    value = copy.deepcopy(ir)
    edits = []
    try:
        artifacts = binding_assembly.unique_ids(value['artifacts'], 'artifact_id')
        intents = binding_assembly.unique_ids(value['service_intents'], 'intent_id')
        bindings = binding_assembly.unique_ids(value['bindings'], 'intent_id')
        if set(intents) != set(bindings):
            raise ValueError('Intent/binding rosters disagree')
        written = {p['artifact_id'] for b in value['bindings'] for p in b['output_bindings']}
        read = {p['artifact_id'] for b in value['bindings'] for p in b['input_bindings']}
        read.update(identity for intent in value['service_intents'] for identity in intent['inputs'])
        for rule in contract['rules']:
            for index, binding in enumerate(value['bindings']):
                if binding['service_id'] != rule['service_id'] or binding['service_version'] != rule['service_version']:
                    continue
                if binding.get('parameter_bindings', {}).get('operation_profile') != rule['operation_profile']:
                    raise ValueError('Output projection cannot reinterpret an unknown operation label')
                producer = binding['intent_id']
                declared = [a for a in artifacts.values() if a.get('producer') == producer and a.get('role') == rule['artifact_role']]
                orphan = [a for a in declared if a['artifact_id'] not in written]
                if not orphan:
                    continue
                if len(declared) != 1 or len(orphan) != 1:
                    raise ValueError('Auxiliary report choice is ambiguous; no completion')
                artifact = orphan[0]
                identity = artifact['artifact_id']
                if (artifact.get('kind') != 'artifact' or artifact.get('data_type') not in rule['artifact_data_types']
                        or artifact.get('consumers') or identity in read or artifact.get('fixture_ref')
                        or artifact.get('external_system_ref')
                        or identity not in intents[producer]['outputs']):
                    raise ValueError('Report completion requires an existing unused declared JSON report/output intention')
                descriptor, error = catalog_get(binding['service_id'], binding['service_version'])
                if error or descriptor is None:
                    raise ValueError('Public output descriptor unavailable')
                ports = [p for p in descriptor.get('interface', {}).get('outputs', []) if p['name'] == rule['port']]
                if (len(ports) != 1 or ports[0].get('channel') != 'artifact' or ports[0].get('cardinality') != 'many'
                        or ports[0].get('data_type') not in ('any', 'json', 'object')):
                    raise ValueError('Public port does not support the registered auxiliary projection')
                existing = [p for p in binding['output_bindings'] if p['port'] == rule['port']]
                if (len(existing) != 1 or artifacts[existing[0]['artifact_id']].get('role') != 'output'
                        or artifacts[existing[0]['artifact_id']].get('data_type') not in ('any', 'json', 'object')):
                    raise ValueError('Require one unambiguous existing primary publication')
                new_binding = {'port': rule['port'], 'artifact_id': identity}
                edits.append({'op': 'add', 'path': f'/bindings/{index}/output_bindings/-', 'value': new_binding,
                    'rule': 'complete_declared_registered_auxiliary_projection',
                    'evidence': {'producer': producer, 'artifact_role': artifact['role'], 'data_type': artifact['data_type'],
                                 'service_id': binding['service_id'], 'service_version': binding['service_version'],
                                 'public_port': rule['port'], 'cardinality': ports[0]['cardinality'], 'projection': rule['projection']}})
                binding['output_bindings'].append(new_binding)
                written.add(identity)
        value, assembly = binding_assembly.assemble(value, catalog_get, assembly_policy)
        if assembly['state'] == 'blocked_no_changes':
            raise ValueError('IR assembly is ambiguous: ' + '; '.join(assembly['blocked_reasons']))
        edits.extend(assembly['operations'])
        verify_protected(original, value, edits)
        return value, {'state': 'completed' if edits else 'unchanged', 'operations': edits,
                       'projection_contract_version': contract['projection_contract_version'],
                       'interpretation': 'New declared compiler elaboration; not lossless raw-output recovery or an original score.',
                       'semantic_outcome': 'not_measured'}
    except (ValueError, KeyError, TypeError) as exc:
        return original, {'state': 'blocked_no_changes', 'operations': [], 'reason': str(exc), 'semantic_outcome': 'not_measured'}


def verify_protected(before, after, edits):
    for key in before:
        if key not in ('bindings', 'artifacts', 'service_intents') and before[key] != after[key]:
            raise ValueError('Protected top-level field changed')
    if after['artifacts'][:len(before['artifacts'])] != before['artifacts']:
        raise ValueError('Existing artifact metadata changed')
    if len(before['bindings']) != len(after['bindings']) or len(before['service_intents']) != len(after['service_intents']):
        raise ValueError('Service or intent roster changed')
    for index, (old, new) in enumerate(zip(before['bindings'], after['bindings'])):
        if {k: v for k, v in old.items() if k != 'output_bindings'} != {k: v for k, v in new.items() if k != 'output_bindings'}:
            raise ValueError('Service, parameter or input choice changed')
        appended = [e['value'] for e in edits if e['path'] == f'/bindings/{index}/output_bindings/-']
        # The narrower status-declaration assembly never changes a binding.
        if new['output_bindings'] != old['output_bindings'] + appended:
            raise ValueError('Existing output binding changed')
    for old, new in zip(before['service_intents'], after['service_intents']):
        if {k: v for k, v in old.items() if k not in ('inputs', 'outputs')} != {k: v for k, v in new.items() if k not in ('inputs', 'outputs')}:
            raise ValueError('Intent decision changed')
