"""Evaluation-only path association; never alter files, values or composition."""
from __future__ import annotations

import copy
from pathlib import PurePosixPath


def associated_path(assertion, reference, mappings, submitted, writers):
    path = PurePosixPath(assertion['path'])
    if path.parent.as_posix() != 'artifacts': return {'state': 'literal_unmapped', 'path': assertion['path']}
    artifact_id = path.stem
    roles = [(r['intent_id'], port) for r in mappings.get('mappings', []) for port, value in r.get('outputs', {}).items()
             if artifact_id in ([value] if isinstance(value, str) else value if isinstance(value, list) else [])]
    if not roles: return {'state': 'literal_unmapped', 'path': assertion['path']}
    gold_bindings = reference.get('bindings', []); source_bindings = submitted.get('bindings', [])
    gold_intents = {i['intent_id']: i for i in reference.get('service_intents', [])}
    source_intents = {i['intent_id']: i for i in submitted.get('service_intents', [])}
    candidates = set(); associations = []
    for intent, port in roles:
        targets = [b for b in gold_bindings if b.get('intent_id') == intent]
        if len(targets) != 1: return {'state': 'unresolved_reference_role', 'path': None}
        target = targets[0]
        eligible = [b for b in source_bindings if (b.get('service_id'), b.get('service_version')) == (target.get('service_id'), target.get('service_version'))]
        exact = [b for b in eligible if b.get('intent_id') == intent]
        if len(exact) == 1: eligible = exact
        elif len(eligible) > 1:
            steps = set(gold_intents.get(intent, {}).get('source_step_refs') or [])
            eligible = [b for b in eligible if steps and set(source_intents.get(b['intent_id'], {}).get('source_step_refs') or []) == steps]
        if len(eligible) != 1: return {'state': 'ambiguous_or_missing_service_role', 'path': None}
        binding = eligible[0]
        bound = [r['artifact_id'] for r in binding.get('output_bindings', []) if r.get('port') == port]
        if len(bound) != 1: return {'state': 'ambiguous_or_missing_output_port', 'path': None}
        found = {w['path'] for w in writers if w['intent_id'] == binding['intent_id'] and w['artifact_id'] == bound[0]}
        if len(found) != 1: return {'state': 'unresolved_actual_writer', 'path': None}
        candidates.update(found); associations.append({'reference_intent': intent, 'model_intent': binding['intent_id'], 'port': port, 'model_artifact': bound[0]})
    if len(candidates) != 1: return {'state': 'ambiguous_output_roles', 'path': None}
    return {'state': 'unique_output_role', 'path': next(iter(candidates)), 'associations': associations}


def predicate_copy(assertion, association):
    if association.get('path') is None: return None
    result = copy.deepcopy(assertion); result['path'] = association['path']
    return result
