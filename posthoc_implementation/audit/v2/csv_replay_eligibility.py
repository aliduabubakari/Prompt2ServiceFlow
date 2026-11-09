"""Read-only checks of saved choices; no repairs, code execution or adapters."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator
import yaml

SENSOR = 'file_location_availability_sensor'
VALIDATOR = 'csv_tabular_schema_validating_loader'
SNAPSHOT = 'database_csv_snapshot_importer'
TABULAR = 'tabular_dataset_database_loader'
PORTS = {
    SENSOR: ({'file_location_resource': 'object'}, {'availability_decision': 'decision', 'check_status': 'status'}),
    VALIDATOR: ({'csv_file': 'csv'}, {'validated_dataset': 'table', 'validated_data_object': 'object', 'validation_status': 'status'}),
    SNAPSHOT: ({'csv_snapshot': 'csv', 'target_database': 'object'}, {'target_database_reference': 'object', 'load_status': 'status'}),
    TABULAR: ({'ingested_data_object': 'object', 'target_database': 'object'}, {'load_status': 'status'})}


def read_saved(path, maximum=2097152, nodes=100000):
    path = Path(path)
    if not path.is_file(): return None, 'missing_saved_artifact'
    if path.stat().st_size > maximum: return None, 'inspection_limit'
    try:
        raw = path.read_text()
        if any(isinstance(t, yaml.tokens.AliasToken) for t in yaml.scan(raw)):
            return None, 'yaml_aliases_require_separate_review'
        value = list(yaml.safe_load_all(raw))
        stack = [(value, 0)]; count = 0
        while stack:
            node, depth = stack.pop(); count += 1
            if count > nodes or depth > 80: return None, 'inspection_limit'
            if isinstance(node, dict):
                if any(not isinstance(k, str) for k in node): return None, 'non_json_document_shape'
                stack.extend((x, depth + 1) for x in node.values())
            elif isinstance(node, list): stack.extend((x, depth + 1) for x in node)
        json.dumps(value, allow_nan=False)
        return value, None
    except (ValueError, TypeError, UnicodeError, yaml.YAMLError, RecursionError):
        return None, 'parse_or_non_json_shape_error'


def contains_template(value):
    if isinstance(value, str): return any(t in value for t in ('{{', '${', '{workspace}', '{fixtures}'))
    if isinstance(value, dict): return any(contains_template(v) for v in value.values())
    if isinstance(value, list): return any(contains_template(v) for v in value)
    return False


def safe(root, relative):
    if not isinstance(relative, str) or not relative or '://' in relative: raise ValueError('Not a local explicit fixture link')
    root = Path(root).resolve(); path = Path(relative); target = (root / path).resolve()
    if path.is_absolute() or '..' in path.parts or not target.is_relative_to(root): raise ValueError('Fixture path escapes root')
    return target


def fixture(workspace, artifact):
    reference = artifact.get('fixture_ref')
    if not reference: return None, 'no_explicit_fixture_ref'
    if contains_template(reference): return None, 'unresolved_fixture_template'
    try:
        parts = Path(reference).parts
        if parts[:2] == ('fixtures', 'inputs') and len(parts) > 2:
            # Declared scenario-neutral convention: exact relative path only.
            target = safe(Path(workspace) / 'fixtures/scenarios/nominal', Path(*parts[2:]).as_posix())
        else: target = safe(workspace, reference)
        return (target, None) if target.is_file() else (None, 'explicit_fixture_missing')
    except (ValueError, TypeError, OSError): return None, 'unsafe_or_nonlocal_fixture_ref'


def direct_inventory(documents):
    resources = []
    for document in documents:
        if isinstance(document, dict) and document.get('kind') == 'List': resources.extend(document.get('items', []))
        else: resources.append(document)
    workflows = [r for r in resources if isinstance(r, dict) and r.get('kind') in ('Workflow', 'CronWorkflow')]
    if not workflows: return {'state': 'direct_argo_shape_error', 'execution_ready': False, 'workflow_resources': 0}
    templates = []
    for r in workflows:
        spec = r.get('spec') or {}
        if r['kind'] == 'CronWorkflow': spec = spec.get('workflowSpec') or {}
        if not isinstance(spec.get('templates'), list):
            return {'state': 'direct_argo_shape_error', 'execution_ready': False, 'workflow_resources': len(workflows)}
        templates.extend(spec['templates'])
    if not templates or any(not isinstance(t, dict) for t in templates):
        return {'state': 'direct_argo_shape_error', 'execution_ready': False, 'workflow_resources': len(workflows)}
    return {'state': 'direct_argo_separate_route_required', 'execution_ready': False,
        'workflow_resources': len(workflows), 'script_templates': sum('script' in t for t in templates),
        'container_templates': sum('container' in t for t in templates),
        'note': 'YAML/resource inventory only. No script execution, IR conversion, service eligibility or semantic score.'}


def analyze_ir(ir, workspace, contract, source_sha, schema=None):
    findings = []
    def add(category, code, subject): findings.append({'category': category, 'code': code, 'subject': str(subject)})
    if not isinstance(ir, dict):
        return {'state': 'invalid_ir_shape', 'execution_ready': False, 'findings': [{'category': 'saved_structure', 'code': 'ir_not_mapping', 'subject': 'document'}]}
    if schema is not None:
        # The caller supplies a pinned schema with local-only references.
        for error in list(Draft202012Validator(schema).iter_errors(ir))[:100]:
            add('saved_structure', 'ir_schema_error', '$' + ''.join('[' + str(p) + ']' for p in error.absolute_path) + ': ' + error.validator)
    required_lists = ['bindings', 'artifacts', 'service_intents']
    if any(not isinstance(ir.get(k), list) or not all(isinstance(v, dict) for v in ir[k]) for k in required_lists):
        add('saved_structure', 'missing_ir_arrays', ','.join(required_lists))
        return result(findings)
    def index(rows, name):
        out = {}
        for row in rows:
            identity = row.get(name)
            if not isinstance(identity, str): add('saved_structure', 'invalid_identity', name); continue
            if identity in out: add('saved_structure', 'duplicate_identity', identity)
            else: out[identity] = row
        return out
    artifacts = index(ir['artifacts'], 'artifact_id'); intents = index(ir['service_intents'], 'intent_id'); bindings = index(ir['bindings'], 'intent_id')
    if set(intents) != set(bindings): add('saved_structure', 'intent_binding_identity_mismatch', 'service_intents/bindings')
    expected_services = Counter([SENSOR, VALIDATOR, contract['loader_service']])
    if Counter(b.get('service_id') for b in bindings.values() if isinstance(b.get('service_id'), str)) != expected_services:
        add('backend_subset', 'outside_three_stage_control_roster', 'bindings')
    runtime = ir.get('runtime') if isinstance(ir.get('runtime'), dict) else {}
    if not isinstance(runtime.get('execution_profile'), str):
        add('public_input_context', 'runtime_profile_not_explicit', 'runtime.execution_profile')
    elif runtime.get('execution_profile') != 'reference':
        add('runtime_interpretation', 'saved_runtime_not_real_reference', 'runtime.execution_profile')
    input_links, output_links, by_service, consumers = {}, {}, {}, {}
    for intent, binding in bindings.items():
        service = binding.get('service_id')
        if not isinstance(service, str): add('saved_structure', 'invalid_service_identity', intent); continue
        by_service.setdefault(service, []).append(intent)
        if service not in PORTS:
            add('backend_subset', 'unregistered_service', service); continue
        if binding.get('service_version') != '1.0.0': add('backend_subset', 'unsupported_service_version', intent)
        if binding.get('secret_bindings'): add('backend_subset', 'secret_dependent_binding', intent)
        for direction, expected in [('input', PORTS[service][0]), ('output', PORTS[service][1])]:
            rows = binding.get(direction + '_bindings')
            if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
                add('saved_structure', 'malformed_port_bindings', intent + ':' + direction); rows = []
            grouped = {}
            for bound in rows:
                port, aid = bound.get('port'), bound.get('artifact_id')
                if not isinstance(port, str) or not isinstance(aid, str): add('saved_structure', 'malformed_port_binding', intent); continue
                grouped.setdefault(port, []).append(aid)
                artifact = artifacts.get(aid)
                if artifact is None: add('saved_structure', 'undeclared_bound_artifact', intent + ':' + aid); continue
                if port in expected and artifact.get('data_type') != expected[port]:
                    add('saved_structure', 'port_artifact_type_mismatch', intent + ':' + port + ':' + aid)
                if direction == 'input': consumers.setdefault(aid, set()).add(intent)
                elif artifact.get('producer') != intent: add('saved_structure', 'output_producer_mismatch', aid)
            if set(grouped) != set(expected): add('saved_structure', 'required_or_unknown_ports', intent + ':' + direction)
            if any(len(v) != 1 for v in grouped.values()): add('saved_structure', 'duplicate_one_valued_port', intent + ':' + direction)
            mapped = {k: v[0] for k, v in grouped.items() if len(v) == 1}
            (input_links if direction == 'input' else output_links)[intent] = mapped
            original_intent = intents.get(intent, {})
            declared = original_intent.get(direction + 's')
            if (not isinstance(declared, list) or not all(isinstance(a, str) for a in declared)
                    or set(declared) != {a for values in grouped.values() for a in values}):
                add('saved_structure', 'redundant_intent_lists_disagree', intent + ':' + direction)
        p = binding.get('parameter_bindings')
        if not isinstance(p, dict): add('saved_structure', 'parameters_not_mapping', intent); continue
        if contains_template(p): add('runtime_interpretation', 'unresolved_parameter_template', intent)
        if service == SENSOR:
            if set(p) - {'location_type', 'path', 'availability_condition'}: add('backend_subset', 'unsupported_sensor_parameters', intent)
            if p.get('location_type') != 'filesystem' or p.get('availability_condition') != 'exists':
                add('backend_subset', 'unsupported_sensor_transport_or_condition', intent)
            if not isinstance(p.get('path'), str) or not p['path']:
                add('saved_structure', 'missing_or_invalid_sensor_path', intent)
            else:
                try: safe(Path(workspace) / 'fixtures/scenarios/nominal', p['path'])
                except (TypeError, ValueError): add('runtime_interpretation', 'sensor_path_needs_resource_mapping', intent)
        elif service == VALIDATOR:
            if set(p) - {'required_columns', 'has_header', 'delimiter', 'fail_on_empty', 'output_path', 'expected_schema'}:
                add('backend_subset', 'unsupported_validation_parameters', intent)
            if p.get('has_header', True) is not True or p.get('delimiter', ',') != ',' or p.get('expected_schema'):
                add('backend_subset', 'unsupported_csv_format_or_typed_schema', intent)
            if any(k in p and not isinstance(p[k], bool) for k in ('has_header', 'fail_on_empty')):
                add('saved_structure', 'non_boolean_validation_flag', intent)
            required = p.get('required_columns')
            if not isinstance(required, list) or not all(isinstance(c, str) for c in required):
                add('backend_subset', 'required_columns_not_explicit', intent)
            else:
                if len(required) != len(set(required)): add('saved_structure', 'duplicate_required_columns', intent)
                missing = sorted(set(required) - set(contract['required_columns']))
                if missing: add('public_input_context', 'required_columns_absent_from_public_csv', intent + ':' + ','.join(missing))
                if set(contract['required_columns']) - set(required): add('backend_subset', 'weaker_than_reference_validation_contract', intent)
            path = p.get('output_path')
            if not isinstance(path, str) or not path: add('saved_structure', 'missing_validation_output_path', intent)
            elif contains_template(path): pass
            elif path != 'artifacts/validated_dataset.json': add('backend_subset', 'validation_output_path_needs_verified_adapter', intent)
        elif service in (SNAPSHOT, TABULAR):
            if service == SNAPSHOT:
                if set(p) != {'import_spec', 'load_mode', 'has_header', 'delimiter'}:
                    add('backend_subset', 'snapshot_parameter_subset_mismatch', intent)
                spec = p.get('import_spec')
                if not isinstance(spec, dict) or set(spec) != {'target_table'}:
                    add('backend_subset', 'unsupported_or_missing_import_spec', intent); table = None
                else: table = spec['target_table']
                mode = p.get('load_mode')
                if p.get('has_header') is not True or p.get('delimiter') != ',': add('backend_subset', 'snapshot_format_not_explicit_supported_subset', intent)
            else:
                if set(p) != {'target_table', 'write_mode'}: add('backend_subset', 'tabular_parameter_subset_mismatch', intent)
                table, mode = p.get('target_table'), p.get('write_mode')
            if not isinstance(table, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,62}', table):
                add('backend_subset', 'unsupported_or_missing_target_table', intent)
            if mode not in ('append', 'replace'): add('backend_subset', 'unsupported_or_missing_write_mode', intent + ':' + str(mode))
    # Every external data/resource choice must be explicitly bound. A system
    # name, a unique available CSV or a template is never used to fill a link.
    for intent, ports in input_links.items():
        for port, aid in ports.items():
            artifact = artifacts.get(aid)
            if not artifact: continue
            producer = artifact.get('producer')
            if producer:
                if not isinstance(producer, str) or producer not in bindings:
                    add('saved_structure', 'unknown_or_multiple_input_producer', aid); continue
                if port == 'ingested_data_object' and output_links.get(producer, {}).get('validated_data_object') != aid:
                    add('saved_structure', 'metadata_port_not_from_validator_object', aid)
                if port == 'csv_file' and bindings.get(producer, {}).get('service_id') == SENSOR:
                    add('saved_structure', 'sensor_decision_is_not_csv_data', aid)
                if port in ('target_database', 'file_location_resource'):
                    add('backend_subset', 'resource_not_explicit_external_fixture', aid)
                if producer == intent: add('saved_structure', 'self_produced_input_dependency', aid)
                continue
            if port == 'ingested_data_object':
                add('saved_structure', 'external_metadata_bypasses_validator_object', aid)
            path, error = fixture(workspace, artifact)
            if error: add('public_input_context', error, intent + ':' + port + ':' + aid); continue
            if port in ('csv_file', 'csv_snapshot'):
                import hashlib
                if hashlib.sha256(path.read_bytes()).hexdigest() != source_sha:
                    add('public_input_context', 'bound_csv_differs_from_control_source', aid)
            elif port in ('target_database', 'file_location_resource'):
                try: resource = json.loads(path.read_text())
                except (ValueError, UnicodeError): add('public_input_context', 'resource_fixture_not_json', aid); continue
                expected = (contract['resource'] if port == 'target_database' else contract['file_location_resource'])
                if resource != expected: add('runtime_interpretation', 'resource_requires_explicit_rebinding', aid)
    for aid, artifact in artifacts.items():
        declared = artifact.get('consumers')
        if (not isinstance(declared, list) or not all(isinstance(v, str) for v in declared)
                or set(declared) != consumers.get(aid, set())):
            add('saved_structure', 'artifact_consumers_disagree', aid)
        if artifact.get('producer') and not any(aid in v.values() for v in output_links.values()):
            add('saved_structure', 'produced_artifact_has_no_bound_writer', aid)
        ref = artifact.get('schema_ref')
        if ref:
            try:
                if not safe(workspace, ref).is_file(): raise ValueError('missing')
            except (ValueError, OSError): add('public_input_context', 'artifact_schema_ref_not_local_available_file', aid)
    flow = ir.get('control_flow')
    if not isinstance(flow, dict): add('saved_structure', 'missing_control_flow', 'control_flow'); flow = {}
    if flow.get('branches') or flow.get('parallel_groups'): add('backend_subset', 'unsupported_branch_or_parallel_semantics', 'control_flow')
    graph = {i: set() for i in bindings}
    edges = flow.get('edges', [])
    if not isinstance(edges, list): add('saved_structure', 'malformed_control_edges', 'control_flow'); edges = []
    for edge in edges:
        if (not isinstance(edge, dict) or set(edge) != {'from', 'to'}
                or not isinstance(edge['from'], str) or not isinstance(edge['to'], str)
                or edge['from'] not in graph or edge['to'] not in graph):
            add('saved_structure', 'invalid_control_edge', 'control_flow.edges'); continue
        graph[edge['from']].add(edge['to'])
    def reaches(start, end):
        todo = list(graph.get(start, [])); seen = set()
        while todo:
            node = todo.pop()
            if node == end: return True
            if node not in seen: seen.add(node); todo.extend(graph.get(node, []))
        return False
    if any(reaches(n, n) for n in graph): add('saved_structure', 'control_cycle', 'control_flow')
    if all(len(by_service.get(s, [])) == 1 for s in expected_services):
        sensor, validator, loader = [by_service[s][0] for s in (SENSOR, VALIDATOR, contract['loader_service'])]
        if not reaches(sensor, validator) or not reaches(validator, loader): add('saved_structure', 'declared_stage_dependencies_missing', 'control_flow')
        gates = flow.get('gates', [])
        if not isinstance(gates, list): add('saved_structure', 'malformed_gates', 'control_flow'); gates = []
        decision = output_links.get(sensor, {}).get('availability_decision')
        covered = set()
        for gate in gates:
            if (not isinstance(gate, dict) or gate.get('sensor_intent') != sensor
                    or gate.get('condition') != str(decision) + '.available == true'):
                add('backend_subset', 'gate_condition_requires_verified_translation', 'control_flow.gates'); continue
            targets = gate.get('gated_intents', [])
            if (not isinstance(targets, list) or not all(isinstance(t, str) for t in targets)
                    or not set(targets).issubset(graph)):
                add('saved_structure', 'invalid_gate_targets', 'control_flow.gates'); continue
            covered.update(targets)
        if validator not in covered: add('backend_subset', 'missing_file_gate_not_explicitly_supported', 'control_flow.gates')
    return result(findings)


def result(findings):
    unique = {(v['category'], v['code'], v['subject']): v for v in findings}
    values = list(unique.values()); nonruntime = [v for v in values if v['category'] != 'runtime_interpretation']
    return {'state': 'blocked_saved_contract' if nonruntime else ('runtime_intervention_candidate_pending_design' if values else 'static_contract_candidate_pending_adapter'),
        'findings': values, 'finding_categories': dict(Counter(v['category'] for v in values)),
        'static_contract_match': not values, 'non_runtime_checks_without_findings': not nonruntime,
        'execution_ready': False, 'adapter_status': 'no_verified_ir_execution_adapter', 'semantic_outcome': 'not_measured'}
