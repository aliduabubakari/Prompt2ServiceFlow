"""Exact public service registry for relational fusion; no mock fallback."""
from __future__ import annotations

from collections import Counter, defaultdict
import re
from types import SimpleNamespace

import fusion_ops as ops
import retention_adapter

BACKEND_ID = 'p2sf.semantic.relational/1'
OPERATIONS = {
    'api_table_primary_source_ingestor': ('ingest_primary_source', 'primary'),
    'api_table_secondary_source_ingestor': ('ingest_secondary_source', 'secondary'),
    'api_table_reference_source_ingestor': ('ingest_reference_source', 'reference'),
    'api_table_multi_source_contract_validator': ('validate_source_contracts', 'validate'),
    'api_table_multi_source_normalizer': ('normalize_sources', 'normalize'),
    'api_table_source_fusion_reconciler': ('fuse_sources', 'reconcile'),
    'api_table_output_bundle_publisher': ('publish_outputs', 'publish')}
window = SimpleNamespace(OPERATIONS=OPERATIONS)
digest, verify_profile = ops.digest, ops.verify_profile


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch('[a-z][a-z0-9_]*', value): raise ValueError('Unsafe identity')
    return value


def compile_plan(ir, profile):
    verify_profile(profile)
    if ir['runtime']['execution_profile'] != 'reference': raise ops.Unsupported('Explicit reference runtime required')
    intents = {i['intent_id']: i for i in ir['service_intents']}
    bindings = {b['intent_id']: b for b in ir['bindings']}
    artifacts = {a['artifact_id']: a for a in ir['artifacts']}
    if len(intents) != len(ir['service_intents']) or len(bindings) != len(ir['bindings']) or len(artifacts) != len(ir['artifacts']) or set(intents) != set(bindings):
        raise ValueError('Duplicate or unmatched identities')
    if Counter(b['service_id'] for b in bindings.values()) != Counter(OPERATIONS.keys()):
        raise ops.Unsupported('Each registered operation is required once in this family')
    flow = ir['control_flow']
    if set(flow) - {'edges', 'branches', 'gates', 'parallel_groups'} or flow.get('branches') or flow.get('gates'):
        raise ops.Unsupported('Unsupported control semantics')
    parents, consumers, writers, projections = {i: set() for i in intents}, defaultdict(set), {}, {}
    for intent, b in bindings.items():
        identifier(intent)
        if b['service_version'] != '1.0.0' or b.get('secret_bindings'): raise ops.Unsupported('Unregistered version/secret')
        p = b.get('parameter_bindings', {})
        if set(p) - {'operation_profile', 'modality_policy'} or p.get('operation_profile') != OPERATIONS[b['service_id']][0]:
            raise ops.Unsupported('Unregistered operation/parameter')
        policy = p.get('modality_policy', {})
        if set(policy) - {'batch', 'true_streaming'} or policy.get('true_streaming', False) is not False or ('batch' in policy and policy['batch'] is not True):
            raise ops.Unsupported('Bounded batch only')
        for field, ports in [('inputs', 'input_bindings'), ('outputs', 'output_bindings')]:
            if set(intents[intent][field]) != {r['artifact_id'] for r in b[ports]}: raise ValueError('Redundant lists disagree')
        incoming = b['input_bindings']
        count = 3 if OPERATIONS[b['service_id']][1] == 'validate' else 1
        if len(incoming) != count or len({i['artifact_id'] for i in incoming}) != count or any(i['port'] != 'input_artifacts' for i in incoming):
            raise ops.Unsupported('Three distinct validator inputs; one bundle for other operations')
        for port in incoming:
            a = artifacts[port['artifact_id']]; consumers[a['artifact_id']].add(intent)
            if a['data_type'] not in ('json', 'object', 'any'): raise ops.Unsupported('JSON bundle required')
            if a.get('producer'):
                if not isinstance(a['producer'], str) or a['producer'] not in parents: raise ValueError('Unknown producer')
                parents[intent].add(a['producer'])
            else:
                ref = a.get('fixture_ref')
                if a.get('role') != 'input' or not isinstance(ref, str) or not ref.startswith('fixtures/inputs/') or retention_adapter.fixture_relative(ref).suffix != '.json':
                    raise ops.Unsupported('Explicit scenario-neutral manifest required')
        data = [o for o in b['output_bindings'] if o['port'] == 'output_artifacts']
        status = [o for o in b['output_bindings'] if o['port'] == 'execution_report']
        if len(status) != 1 or len(data) not in (1, 2) or len(data) + len(status) != len(b['output_bindings']):
            raise ops.Unsupported('One primary JSON bundle and status required; optional publisher audit')
        audit = []
        if len(data) == 2:
            if OPERATIONS[b['service_id']][1] != 'publish': raise ops.Unsupported('Only publisher audit projection is registered')
            audit = [o for o in data if artifacts[o['artifact_id']]['role'] == 'report' and artifacts[o['artifact_id']]['data_type'] in ('json', 'object')]
            data = [o for o in data if artifacts[o['artifact_id']]['role'] == 'output']
            if len(audit) != 1 or len(data) != 1: raise ops.Unsupported('Ambiguous publication projections')
            identity = audit[0]['artifact_id']
            if artifacts[identity]['consumers']: raise ops.Unsupported('Audit cannot feed computation')
        main, report = artifacts[data[0]['artifact_id']], artifacts[status[0]['artifact_id']]
        if main['role'] not in ('output', 'intermediate') or main['data_type'] not in ('any', 'json', 'object') or report['data_type'] != 'status' or report['role'] not in ('status', 'report'):
            raise ops.Unsupported('Explicit JSON/status output roles required')
        projections[intent] = {'primary': main['artifact_id'], 'status': report['artifact_id'], 'audit': [o['artifact_id'] for o in audit]}
        for port in b['output_bindings']:
            a = artifacts[identifier(port['artifact_id'])]
            if a.get('producer') != intent or a['artifact_id'] in writers: raise ValueError('Conflicting writer')
            if a.get('media_type') not in (None, 'application/json'): raise ops.Unsupported('Bound artifacts are JSON')
            writers[a['artifact_id']] = intent
    for a in artifacts.values():
        if set(a['consumers']) != consumers[a['artifact_id']]: raise ValueError('Consumers disagree')
        if a.get('producer') and a['artifact_id'] not in writers: raise ValueError('Unbound produced artifact')
    for edge in flow['edges']:
        if set(edge) != {'from', 'to'} or edge['from'] not in parents or edge['to'] not in parents: raise ValueError('Invalid edge')
        parents[edge['to']].add(edge['from'])
    pending, order = set(parents), []
    while pending:
        ready = sorted(i for i in pending if parents[i].issubset(order))
        if not ready: raise ValueError('Dependency cycle')
        order.extend(ready); pending.difference_update(ready)
    for group in flow.get('parallel_groups', []):
        members = set(group['intent_ids'])
        if not members.issubset(parents): raise ValueError('Unknown parallel member')
        for member in members:
            ancestors, frontier = set(), set(parents[member])
            while frontier:
                node = frontier.pop()
                if node not in ancestors: ancestors.add(node); frontier.update(parents[node])
            if ancestors & members: raise ops.Unsupported('Dependent stages cannot be a parallel group')
    return {'backend_id': BACKEND_ID, 'order': order, 'parents': {i: sorted(p) for i, p in parents.items()},
            'outputs': projections, 'strict_labels_verified': True, 'label_replacements': [], 'mock_fallback': False}
