"""Public-task compiler control and reproducible input perturbations.

Control graphs and evaluation variants are evaluator-only and never staged for
model methods. No native reference code or private v1 assertions are loaded.
"""
from __future__ import annotations

import copy
import csv
import io
import json
from pathlib import Path
import re
import shutil

import fusion_backend as backend


def reference_ir(metadata, task_text):
    labels = [v[0] for v in backend.OPERATIONS.values()]
    services = list(backend.OPERATIONS)
    edges = [(labels[i], labels[3]) for i in range(3)] + list(zip(labels[3:], labels[4:]))
    parents = {i: [a for a, b in edges if b == i] for i in labels}
    artifacts = [{'artifact_id': 'external_manifest', 'name': 'Public source manifest', 'kind': 'artifact', 'data_type': 'json',
                  'role': 'input', 'producer': None, 'consumers': labels[:3], 'fixture_ref': 'fixtures/inputs/fixture.json',
                  'sensitivity': 'internal', 'persistence': 'workflow'}]
    intents, bindings = [], []
    lines = task_text.splitlines()
    for index, (intent, service) in enumerate(zip(labels, services)):
        input_ids = [p + '_bundle' for p in parents[intent]] if parents[intent] else ['external_manifest']
        output_ids = [intent + '_bundle', intent + '_status'] + (['publication_audit'] if index == 6 else [])
        pattern = r'^\d+\.\s+' + re.escape(intent) + r'\s+-'
        evidence = [line for line in lines if re.match(pattern, line)]
        if len(evidence) != 1: raise ValueError('Missing public source-step evidence for control')
        intents.append({'intent_id': intent, 'name': intent.replace('_', ' ').title(), 'source_step_refs': [intent],
            'capability': 'Perform the publicly specified ' + intent.replace('_', ' ') + ' operation.',
            'category': 'Extractor' if index < 3 else 'Loader' if index == 6 else 'Transformer',
            'inputs': input_ids, 'outputs': output_ids, 'preconditions': [], 'effects': ['Emit the declared real computation and status outputs.'],
            'external_system_refs': [], 'required_policy_properties': {'idempotency': 'required', 'network_access': 'forbidden', 'secret_access': 'forbidden'},
            'confidence': 'explicit', 'evidence': [{'source': 'description', 'text': evidence[0]}],
            'ambiguity': {'status': 'none', 'notes': []}, 'decomposition_rationale': 'One control operation per explicit public task step.'})
        bindings.append({'intent_id': intent, 'service_id': service, 'service_version': '1.0.0',
            'input_bindings': [{'port': 'input_artifacts', 'artifact_id': i} for i in input_ids],
            'output_bindings': [{'port': 'output_artifacts' if not i.endswith('_status') else 'execution_report', 'artifact_id': i} for i in output_ids],
            'parameter_bindings': {'operation_profile': intent}, 'secret_bindings': [], 'confidence': 'explicit',
            'rationale': 'Exercise the registered public service implementation in the compiler control.'})
        for identity in output_ids:
            is_status, is_audit = identity.endswith('_status'), identity == 'publication_audit'
            artifacts.append({'artifact_id': identity, 'name': identity.replace('_', ' ').title(), 'kind': 'artifact',
                'data_type': 'status' if is_status else 'json', 'media_type': 'application/json',
                'role': 'status' if is_status else 'report' if is_audit else 'output' if index == 6 else 'intermediate',
                'producer': intent, 'consumers': [] if is_status or is_audit else [b for a, b in edges if a == intent],
                'sensitivity': 'internal', 'persistence': 'workflow'})
    return {**copy.deepcopy(metadata), 'requirement': {'name': 'Public relational routing control',
            'purpose': 'Join the supplied source records and compute the explicitly declared routing decisions.',
            'domain': 'Marketing/Customer Operations', 'execution_model': 'batch', 'topology': 'fan_out_fan_in', 'information_sufficiency': 'high'},
        'source_step_accounting': [{'source_step_ref': i, 'disposition': 'service', 'intent_ids': [i], 'rationale': 'Explicit public task step.'} for i in labels],
        'service_intents': intents, 'bindings': bindings, 'artifacts': artifacts, 'external_systems': [],
        'control_flow': {'edges': [{'from': a, 'to': b} for a, b in edges], 'branches': [], 'gates': [],
                         'parallel_groups': [{'group_id': 'source_ingestion', 'intent_ids': labels[:3]}]},
        'schedule': {'type': 'manual', 'catchup': False},
        'policies': {'default_retries': 2, 'default_retry_delay_seconds': 300, 'fail_fast': False, 'service_overrides': [],
                     'governance': {'allowed_sensitivities': ['internal', 'confidential', 'pii'], 'network_default': 'forbidden', 'secret_placeholders_only': True}},
        'runtime': {'target': 'argo-workflows', 'version': '3.5.0', 'execution_profile': 'reference', 'namespace': 'default',
                    'service_account': 'default', 'artifact_repository': {'type': 'none', 'reference': None}},
        'validation_expectations': [{'gate': 'G' + str(i), 'expected_status': 'pass', 'checks': ['Validate the public composition contract.']} for i in range(7)]}


def input_bank(public_nominal, destination, profile, design):
    if destination.exists(): raise ValueError('Never overwrite an evaluation fixture bank')
    for scenario in design['positive_scenarios'] + design['rejection_scenarios']:
        target = destination / 'scenarios' / scenario
        shutil.copytree(public_nominal, target)
        if scenario == 'nominal': continue
        manifest = json.loads((target / 'fixture.json').read_text())
        files = {role: target / manifest['inputs'][key] for role, key in profile['inputs'].items()}
        # All mutation paths come from the public manifest and remain contained.
        for path in files.values():
            if not path.resolve().is_relative_to(target.resolve()): raise ValueError('Unsafe scenario source')
        tickets, policy = json.loads(files['primary'].read_text()), json.loads(files['reference'].read_text())
        with files['secondary'].open(newline='') as handle:
            reader = csv.DictReader(handle); header = reader.fieldnames; customers = list(reader)
        f = profile['fields']
        if scenario == 'source_reordering': tickets.reverse(); customers.reverse()
        elif scenario == 'changed_priority': tickets[0][f['priority']] = max(policy['priority_weights'], key=policy['priority_weights'].get)
        elif scenario == 'changed_policy':
            for key in policy['tier_multipliers']: policy['tier_multipliers'][key] *= 2
        elif scenario == 'threshold_boundary':
            priority = min(policy['priority_weights'], key=policy['priority_weights'].get)
            tickets[0][f['priority']] = priority
            tickets[0][f['category']] = 'v2_non_immediate_category'
            customer = next(r for r in customers if r[f['join_key']] == tickets[0][f['join_key']])
            customer[f['churn']] = 'low'
            policy['escalation_threshold'] = policy['priority_weights'][priority] * policy['tier_multipliers'][customer[f['tier']]]
        elif scenario == 'extra_record': tickets.append({**tickets[0], f['record_id']: 'v2_extra_record'})
        elif scenario == 'duplicate_lookup': customers.append(copy.deepcopy(customers[0]))
        elif scenario == 'missing_join_key': tickets[0].pop(f['join_key'])
        elif scenario == 'unknown_priority': tickets[0][f['priority']] = 'v2_unknown_priority'
        else: raise ValueError('Unknown scenario')
        files['primary'].write_text(json.dumps(tickets, indent=2) + '\n')
        files['reference'].write_text(json.dumps(policy, indent=2) + '\n')
        stream = io.StringIO(newline=''); writer = csv.DictWriter(stream, fieldnames=header, lineterminator='\n')
        writer.writeheader(); writer.writerows(customers); files['secondary'].write_text(stream.getvalue())
