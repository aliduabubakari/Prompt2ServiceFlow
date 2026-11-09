"""Explicit, conservative v2 assembly; never infer missing business decisions."""
from __future__ import annotations

from collections import Counter
import copy


def unique_ids(rows, key):
    ids = [row[key] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate identity: ' + key)
    return {row[key]: row for row in rows}


def assemble(document, catalog_get, policy):
    """Return original unchanged on ambiguity; otherwise apply only public rules."""
    original = copy.deepcopy(document)
    candidate = copy.deepcopy(document)
    operations, blocked = [], []
    try:
        artifacts = unique_ids(document['artifacts'], 'artifact_id')
        intents = unique_ids(document['service_intents'], 'intent_id')
        bindings = unique_ids(document['bindings'], 'intent_id')
        if set(intents) != set(bindings):
            raise ValueError('Intent/binding rosters disagree')
        writers = Counter(p['artifact_id'] for b in document['bindings'] for p in b['output_bindings'])
        reads = {p['artifact_id'] for b in document['bindings'] for p in b['input_bindings']}
        reads.update(a for intent in document['service_intents'] for a in intent['inputs'])
        if any(n > 1 for n in writers.values()):
            raise ValueError('Multiple output bindings share an artifact; merge semantics required')
        for binding in document['bindings']:
            intent = binding['intent_id']
            descriptor, error = catalog_get(binding['service_id'], binding['service_version'])
            if error or descriptor is None:
                raise ValueError('Public service descriptor unavailable')
            interface = descriptor['interface']
            input_ports = {p['name']: p for p in interface.get('inputs', [])}
            outputs = {p['name']: p for p in interface.get('outputs', [])}
            for row in binding['input_bindings']:
                if row['port'] not in input_ports:
                    raise ValueError('Unknown public input port')
                if row['artifact_id'] not in artifacts:
                    raise ValueError('Missing input artifact; no source inference allowed')
            counts = Counter(p['port'] for p in binding['output_bindings'])
            for row in binding['output_bindings']:
                identity, port = row['artifact_id'], row['port']
                definition = outputs.get(port)
                if definition is None:
                    raise ValueError('Unknown public output port')
                if identity in artifacts:
                    continue
                if not (definition.get('required') is True and definition.get('channel') == 'artifact'
                        and definition.get('data_type') == 'status' and definition.get('cardinality') == 'one'
                        and counts[port] == 1 and writers[identity] == 1 and identity not in reads):
                    raise ValueError('Missing artifact is not an unambiguous unused required status output')
                artifact = {**copy.deepcopy(policy['status_declaration_metadata']), 'artifact_id': identity,
                            'name': identity, 'producer': intent, 'consumers': []}
                candidate['artifacts'].append(artifact)
                operations.append({'op': 'add', 'path': '/artifacts/-', 'value': artifact,
                                   'rule': 'declare_existing_model_bound_status',
                                   'evidence': {'intent_id': intent, 'port': port, 'artifact_id': identity}})
        for index, intent in enumerate(candidate['service_intents']):
            binding = bindings[intent['intent_id']]
            for target, source in [('inputs', 'input_bindings'), ('outputs', 'output_bindings')]:
                projected = list(dict.fromkeys(p['artifact_id'] for p in binding[source]))
                if intent[target] != projected:
                    operations.append({'op': 'replace', 'path': f'/service_intents/{index}/{target}',
                                       'old_value': copy.deepcopy(intent[target]), 'value': projected,
                                       'rule': 'project_intent_list_from_existing_port_bindings'})
                    intent[target] = projected
    except (ValueError, KeyError, TypeError) as exc:
        blocked.append(str(exc))
        return original, {'state': 'blocked_no_changes', 'blocked_reasons': blocked, 'operations': [],
                          'semantic_outcome': 'not_measured'}
    verify_preservation(original, candidate)
    return candidate, {'state': 'assembled' if operations else 'unchanged', 'blocked_reasons': [],
                       'operations': operations, 'semantic_outcome': 'not_measured'}


def verify_preservation(before, after):
    if set(before) != set(after):
        raise ValueError('Top-level roster changed')
    for key in before:
        if key not in ('artifacts', 'service_intents') and before[key] != after[key]:
            raise ValueError('Protected field changed: ' + key)
    if after['artifacts'][:len(before['artifacts'])] != before['artifacts']:
        raise ValueError('Existing artifact changed')
    if len(before['service_intents']) != len(after['service_intents']):
        raise ValueError('Intent roster changed')
    for old, new in zip(before['service_intents'], after['service_intents']):
        if set(old) != set(new) or any(old[k] != new[k] for k in old if k not in ('inputs', 'outputs')):
            raise ValueError('Protected intent decision changed')
