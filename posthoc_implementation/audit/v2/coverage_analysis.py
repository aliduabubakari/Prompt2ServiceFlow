"""Conservative static coverage analysis, not a workflow validator or scorer.

Reference-side workload planning is kept separate from model-cell diagnostics.
No condition expressions, SQL, source code, containers, or model calls execute.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import service_executor as ports
import workflow_executor as workflow
import retention_adapter
from jsonschema import Draft202012Validator


def service_key(name, version):
    if not isinstance(name, str) or not isinstance(version, str):
        raise ValueError('Service identity/version must be strings')
    return name + '@' + version


def walk(node):
    """Bounded identity-aware traversal also handles YAML anchors/cycles."""
    stack, seen, count = [node], set(), 0
    while stack:
        value = stack.pop()
        count += 1
        if count > 100000:
            raise ValueError('Document traversal limit exceeded')
        if isinstance(value, (dict, list)):
            if id(value) in seen:
                continue
            seen.add(id(value))
            stack.extend(value.values() if isinstance(value, dict) else value)
        yield value


def read_document(path, load, max_bytes):
    if not path.is_file():
        return None, 'missing_artifact'
    if path.stat().st_size > max_bytes:
        return None, 'inspection_limit'
    try:
        value = load(path)
        if not isinstance(value, dict):
            return None, 'invalid_document'
        list(walk(value))
        return value, None
    except Exception as exc:
        return None, 'parse_or_shape_error:' + type(exc).__name__


class Catalog:
    """Lazy public-descriptor cache; private relationships are never loaded."""
    def __init__(self, load):
        self.load = load
        self.indices, self.descriptors, self.inventories = {}, {}, {}

    def get(self, workspace, service, version):
        workspace = workspace.resolve()
        path = workspace / 'catalog/catalog.yaml'
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest not in self.indices:
            entries = self.load(path)['services']
            self.indices[digest] = {(e['service_id'], e['version']): e for e in entries}
        entry = self.indices[digest].get((service, version))
        if not entry:
            return None, 'service_version_absent_from_public_catalog'
        descriptor_path = ports.inside(workspace / 'catalog', entry['descriptor_path'])
        actual = hashlib.sha256(descriptor_path.read_bytes()).hexdigest()
        # The public builder strips descriptor provenance but retains source
        # descriptor pins in catalog.yaml. Verify transformed bytes against
        # workspace.yaml, not against the pre-sanitization source-file hash.
        inventory_path = workspace / 'workspace.yaml'
        if not inventory_path.is_file():
            return None, 'public_workspace_manifest_missing'
        identity = str(inventory_path.resolve())
        if identity not in self.inventories:
            self.inventories[identity] = {e['path']: e['sha256'] for e in self.load(inventory_path)['files']}
        expected = self.inventories[identity].get(descriptor_path.relative_to(workspace).as_posix())
        if expected != actual:
            return None, 'public_descriptor_checksum_mismatch'
        if actual not in self.descriptors:
            self.descriptors[actual] = self.load(descriptor_path)
        descriptor = self.descriptors[actual]
        if descriptor.get('service_id') != service or descriptor.get('version') != version:
            return None, 'public_descriptor_identity_mismatch'
        return descriptor, None


def parameter_review(parameters):
    values = list(walk(parameters))
    return {'unresolved_template': any(isinstance(v, str) and any(t in v for t in ('{{', '${', '{workspace}', '{fixtures}')) for v in values),
            'absolute_location': any(isinstance(v, str) and v.startswith('/') for v in values)}


def schema_review(reference, workspace, load):
    if not isinstance(reference, str) or '://' in reference:
        return {'state': 'unsupported_schema_reference'}
    try:
        path = ports.inside(workspace, reference)
        if not path.is_file():
            return {'state': 'schema_file_missing'}
        schema = load(path)
        Draft202012Validator.check_schema(schema)  # Syntax only; no instance or remote-reference evaluation.
        refs = [v['$ref'] for v in walk(schema) if isinstance(v, dict) and '$ref' in v]
        return {'state': 'reference_resolution_review' if refs else 'schema_syntax_checked',
                'schema_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'reference_count': len(refs), 'schema_type': schema.get('type') if isinstance(schema, dict) else None}
    except Exception as exc:
        return {'state': 'schema_inspection_error', 'error_type': type(exc).__name__}


def analyze_ir(document, workspace, catalog, load, scenarios):
    issues, service_records, input_records, schemas, resource_records = [], [], [], [], []
    def issue(category, code, subject):
        issues.append({'category': category, 'code': code, 'subject': str(subject)})
    bindings, artifacts, intents = document.get('bindings'), document.get('artifacts'), document.get('service_intents')
    if not isinstance(bindings, list) or not bindings or not isinstance(artifacts, list) or not isinstance(intents, list):
        return {'state': 'invalid_ir_structure', 'issues': [{'category': 'format', 'code': 'missing_nonempty_ir_sections', 'subject': 'document'}],
                'services': [], 'missing_services': [], 'service_roster_complete': False, 'execution_ready': False}
    try:
        artifact_map = {a['artifact_id']: a for a in artifacts}
        intent_ids = [i['intent_id'] for i in intents]
        binding_ids = [b['intent_id'] for b in bindings]
        if len(artifact_map) != len(artifacts) or len(set(intent_ids)) != len(intent_ids) or len(set(binding_ids)) != len(binding_ids):
            issue('format', 'duplicate_ir_identifiers', 'document')
        if set(intent_ids) != set(binding_ids):
            issue('format', 'intent_binding_roster_mismatch', 'document')
        dependencies = {i: set() for i in intent_ids}
        writers = Counter()
        for binding in bindings:
            intent, name, version = binding['intent_id'], binding['service_id'], binding['service_version']
            key = service_key(name, version)
            workflow_supported = name in workflow.SUPPORTED and version == '1.0.0'
            standalone = name in ports.REGISTRY and version == ports.REGISTRY[name]['version']
            record = {'intent_id': intent, 'service': key, 'workflow_dispatch_available': workflow_supported,
                      'standalone_operation_available': standalone, 'parameter_review': parameter_review(binding.get('parameter_bindings', {}))}
            descriptor, error = catalog.get(workspace, name, version)
            if error:
                issue('catalog', error, intent)
            record['catalog_state'] = error or 'public_descriptor_present'
            if record['parameter_review']['unresolved_template']:
                issue('control', 'public_template_or_logical_context_required', intent)
            if record['parameter_review']['absolute_location']:
                issue('resource', 'logical_location_mapping_review', intent)
            if descriptor:
                policy = descriptor.get('policies', {})
                record['network_policy'] = policy.get('network_access', 'unknown')
                record['secret_policy'] = policy.get('secret_access', 'unknown')
                record['invocation_type'] = descriptor.get('invocation', {}).get('type', 'unspecified')
                record['runtime_image'] = descriptor.get('invocation', {}).get('image')
                record['declared_gpu'] = policy.get('resources', {}).get('gpu', 0)
                operations = descriptor.get('capability', {})
                wording = ' '.join([name, str(operations.get('summary', '')), *map(str, operations.get('operations', []))]).lower()
                record['destructive_effect_review'] = bool(re.search(r'clean.?up|delet|truncat|\bremove\b|\bdrop\b', wording))
                interface = descriptor.get('interface', {})
                for field, declarations in [('input_bindings', interface.get('inputs', [])), ('output_bindings', interface.get('outputs', []))]:
                    by_name = {d['name']: d for d in declarations}
                    seen = Counter(item['port'] for item in binding.get(field, []))
                    for port, decl in by_name.items():
                        if decl.get('required') is True and port not in seen:
                            issue('input' if field == 'input_bindings' else 'format', 'required_service_port_unbound', intent + ':' + port)
                    for port, count in seen.items():
                        if port not in by_name:
                            issue('format', 'unknown_service_port', intent + ':' + port)
                        elif count > 1:
                            issue('control' if by_name[port].get('cardinality') == 'many' else 'format',
                                  'many_input_dispatch_review' if by_name[port].get('cardinality') == 'many' else 'duplicate_single_port', intent + ':' + port)
                declared_parameters = {p['name']: p for p in interface.get('parameters', [])}
                actual_parameters = binding.get('parameter_bindings', {})
                for param, decl in declared_parameters.items():
                    if decl.get('required') is True and param not in actual_parameters:
                        issue('input', 'required_service_parameter_absent', intent + ':' + param)
                for param in set(actual_parameters) - set(declared_parameters):
                    issue('format', 'parameter_not_in_public_descriptor', intent + ':' + param)
            if name == workflow.SENSOR and workflow_supported:
                parameters = binding.get('parameter_bindings', {})
                if (parameters.get('location_type') != 'filesystem' or parameters.get('availability_condition') != 'exists'
                        or set(parameters) - {'location_type', 'path', 'availability_condition'}):
                    issue('resource', 'sensor_profile_outside_verified_local_subset', intent)
            if name == workflow.CSV and workflow_supported:
                params = binding.get('parameter_bindings', {})
                if params.get('expected_schema') or params.get('has_header') is False:
                    issue('schema', 'csv_rules_outside_verified_subset', intent)
            if binding.get('secret_bindings'):
                issue('resource', 'explicit_secret_binding_review', intent)
            service_records.append(record)
            for item in binding.get('output_bindings', []):
                identity = item['artifact_id']
                writers[identity] += 1
                producer = artifact_map.get(identity, {}).get('producer')
                if identity not in artifact_map or (intent not in producer if isinstance(producer, list) else producer != intent):
                    issue('format', 'output_producer_mismatch', identity)
            for item in binding.get('input_bindings', []):
                identity = item['artifact_id']
                if identity not in artifact_map:
                    issue('input', 'bound_artifact_absent', identity)
                    continue
                artifact = artifact_map[identity]
                producer = artifact.get('producer')
                if producer:
                    producers = producer if isinstance(producer, list) else [producer]
                    if isinstance(producer, list):
                        issue('control', 'multi_producer_merge_semantics_required', identity)
                    for p in producers:
                        if p not in dependencies or intent not in dependencies:
                            issue('control', 'unknown_artifact_producer', identity)
                        else:
                            dependencies[intent].add(p)
                    input_records.append({'intent_id': intent, 'port': item['port'], 'artifact_id': identity, 'kind': 'produced'})
                    continue
                reference = artifact.get('fixture_ref')
                row = {'intent_id': intent, 'port': item['port'], 'artifact_id': identity, 'kind': 'external', 'fixture_ref_present': bool(reference)}
                if not reference:
                    row['state'] = 'missing_explicit_fixture'
                    issue('input', 'missing_explicit_fixture', intent + ':' + item['port'])
                else:
                    try:
                        relative = retention_adapter.fixture_relative(reference).as_posix()
                        row['active_relative_path'] = relative
                        locations = [ports.inside(ports.inside(workspace, s['fixture_root']), relative) for s in scenarios]
                        absent = [s['name'] for s, p in zip(scenarios, locations) if not p.is_file()]
                        row['state'] = 'public_file_unavailable' if absent else 'explicit_public_file_available'
                        row['unavailable_scenarios'] = absent
                        if absent:
                            issue('input', 'public_file_unavailable', intent + ':' + item['port'])
                        # Bounded resource metadata, never credentials, raw URLs,
                        # arbitrary fixture contents, or assertion answers.
                        if locations and locations[0].is_file() and locations[0].suffix == '.json' and locations[0].stat().st_size < 65536:
                            value = load(locations[0])
                            if isinstance(value, dict) and any(k in value for k in ('driver', 'engine', 'provider')):
                                resource_records.append({'intent_id': intent, 'artifact_id': identity,
                                    **{k: value[k] if re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', value[k]) else '<non-label-value>'
                                       for k in ('driver', 'engine', 'provider') if k in value and isinstance(value[k], str)}})
                                if name == workflow.SENSOR and value != {'driver': 'fixture-filesystem', 'root': '.'}:
                                    issue('resource', 'sensor_resource_profile_unverified', intent)
                    except (ValueError, TypeError, OSError):
                        row['state'] = 'fixture_reference_form_unsupported'
                        issue('input', 'fixture_reference_form_unsupported', intent + ':' + item['port'])
                input_records.append(row)
        for identity, count in writers.items():
            if count > 1:
                issue('control' if isinstance(artifact_map.get(identity, {}).get('producer'), list) else 'format',
                      'multi_writer_merge_support_required' if isinstance(artifact_map.get(identity, {}).get('producer'), list) else 'multiple_bound_writers', identity)
        for identity, artifact in artifact_map.items():
            if artifact.get('producer') and identity not in writers:
                issue('input', 'produced_artifact_has_no_writer', identity)
            if artifact.get('schema_ref'):
                check = schema_review(artifact['schema_ref'], workspace, load)
                schemas.append({'artifact_id': identity, **check})
                if check['state'] != 'schema_syntax_checked':
                    issue('schema', check['state'], identity)
        flow = document.get('control_flow', {})
        for edge in flow.get('edges', []):
            if edge['from'] not in dependencies or edge['to'] not in dependencies:
                issue('control', 'unknown_control_endpoint', 'edge')
            else:
                dependencies[edge['to']].add(edge['from'])
            if edge.get('condition'):
                issue('control', 'original_condition_translation_required', 'edge')
        if flow.get('branches'):
            issue('control', 'original_branch_and_merge_translation_required', 'control_flow')
        if flow.get('gates'):
            issue('control', 'original_gate_translation_required', 'control_flow')
        if flow.get('parallel_groups'):
            issue('control', 'original_parallel_fanin_semantics_review', 'control_flow')
        complete, pending = set(), set(dependencies)
        while pending:
            ready = {i for i in pending if dependencies[i].issubset(complete)}
            if not ready:
                issue('control', 'dependency_cycle_or_unresolved_parent', 'control_flow')
                break
            complete.update(ready)
            pending -= ready
        missing = sorted({s['service'] for s in service_records if not s['workflow_dispatch_available']})
        return {'state': 'analyzed', 'binding_count': len(bindings), 'services': service_records,
                'reference_information_sufficiency': document.get('requirement', {}).get('information_sufficiency', 'unspecified'),
                'declared_external_systems': [{k: item.get(k) for k in ('system_id', 'type', 'mock_strategy')}
                                             for item in document.get('external_systems', []) if isinstance(item, dict)],
                'missing_services': missing, 'service_roster_complete': not missing,
                'execution_ready': False, 'readiness_note': 'Static planning only: original-IR translation and complete original reference controls are not yet verified',
                'inputs': input_records, 'schemas': schemas, 'resource_profiles': resource_records,
                'issues': issues, 'issue_counts': dict(Counter(i['category'] for i in issues)),
                'network_required_services': sorted({s['service'] for s in service_records if s.get('network_policy') == 'required'}),
                'credential_review_services': sorted({s['service'] for s in service_records if s.get('secret_policy') == 'required'}),
                'destructive_review_services': sorted({s['service'] for s in service_records if s.get('destructive_effect_review')})}
    except Exception as exc:
        return {'state': 'inspection_error', 'error_type': type(exc).__name__, 'issues': issues,
                'error_message': str(exc)[:160],
                'services': service_records, 'missing_services': [], 'service_roster_complete': False, 'execution_ready': False}


def rank_key(reference):
    analysis = reference['analysis']
    counts = analysis.get('issue_counts', {})
    return (len(analysis['missing_services']), counts.get('control', 0), counts.get('input', 0),
            len(analysis.get('network_required_services', [])) + len(analysis.get('credential_review_services', [])),
            len(analysis.get('destructive_review_services', [])), reference['case'])


def propose_cohorts(references, size):
    # Only reference implementation requirements affect ranking. Model-cell
    # availability, parse rates, old scores, and apparent new successes do not.
    ranked = sorted((r for r in references if r['analysis']['state'] == 'analyzed'), key=rank_key)
    local = [r for r in ranked if not r['analysis'].get('network_required_services')
             and not r['analysis'].get('credential_review_services') and not r['analysis'].get('destructive_review_services')
             and not r['analysis'].get('issue_counts', {}).get('input')]
    seed = (local or ranked)[:1]
    chosen = list(seed)
    if seed:
        required = set(seed[0]['analysis']['missing_services'])
        candidates = [r for r in ranked if r is not seed[0]]
        while candidates and len(chosen) < size:
            # Prefer concrete reuse with already selected missing capabilities.
            shared = [r for r in candidates if required.intersection(r['analysis']['missing_services'])]
            if not shared:
                break
            best = min(shared, key=lambda r: (len(set(r['analysis']['missing_services']) - required), rank_key(r)))
            chosen.append(best)
            required.update(best['analysis']['missing_services'])
            candidates.remove(best)
    return {'reference_ranking': [r['case'] for r in ranked], 'conservative_local_shortlist': [r['case'] for r in local],
            'tentative_shared_implementation_cohort': [r['case'] for r in chosen],
            'cohort_missing_services': sorted({s for r in chosen for s in r['analysis']['missing_services']}),
            'status': 'proposal_requires_review_not_execution_authorization',
            'ranking_note': 'Service count is a workload proxy, not an effort estimate; resource, deletion, schema, and control gaps still require review.'}
