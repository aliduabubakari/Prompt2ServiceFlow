"""Collect independent static findings; never repair, execute, or score an IR.

Catalog violations are separated from the narrower bounded-window adapter and
its new input-mapping rules. Findings can overlap; no first-error short circuit.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path

from jsonschema import Draft202012Validator

CATEGORIES = (
    'saved_structure', 'public_catalog', 'dataflow', 'v2_input_mapping',
    'adapter_limit', 'public_semantics_unspecified', 'inspection_error',
)


def safe_path(root, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError('Expected a relative file reference')
    path = (root / relative).resolve()
    if '..' in Path(relative).parts or not path.is_relative_to(root.resolve()):
        raise ValueError('File reference escapes public root')
    return path


def fixture_file(reference, active):
    """Existing v2 convention, not a claim that v1 required fixture_ref."""
    if not isinstance(reference, str):
        raise ValueError('Missing string fixture reference')
    parts = Path(reference).parts
    if parts[:2] == ('fixtures', 'inputs'):
        relative = parts[2:]
    elif len(parts) > 3 and parts[:2] == ('fixtures', 'scenarios'):
        relative = parts[3:]
    else:
        raise ValueError('Reference form not mapped by the current v2 convention')
    if not relative:
        raise ValueError('Reference has no relative file')
    return safe_path(active, Path(*relative).as_posix())


def analyze(ir, *, schema, catalog_get, active, operations, fixture_keys, load_json,
            max_bytes=2_000_000):
    findings, services, inputs = [], [], []

    def add(category, code, subject, **details):
        findings.append({'category': category, 'code': code, 'subject': str(subject), **details})

    if not isinstance(ir, dict):
        add('saved_structure', 'document_not_object', 'document')
        return result(findings, services, inputs)
    try:
        # Also rejects recursive YAML aliases/non-JSON keys, before JSON-schema
        # traversal. No instance data may introduce an external schema resolver.
        json.dumps(ir, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        add('saved_structure', 'document_not_json_compatible', 'document')
        return result(findings, services, inputs)
    for error in Draft202012Validator(schema).iter_errors(ir):
        # Do not serialize instance values (which might include secret bindings).
        add('saved_structure', 'ir_schema_violation', '/' + '/'.join(map(str, error.absolute_path)),
            validator=error.validator)

    def section(key, identity):
        values = ir.get(key)
        if not isinstance(values, list):
            add('saved_structure', 'section_not_list', key)
            return [], {}
        mapped = {}
        for index, value in enumerate(values):
            if not isinstance(value, dict) or not isinstance(value.get(identity), str):
                add('saved_structure', 'invalid_section_entry', f'{key}/{index}')
                continue
            key_value = value[identity]
            if key_value in mapped:
                add('saved_structure', 'duplicate_identifier', f'{key}/{index}', identifier=key_value)
            else:
                mapped[key_value] = value
        return [v for v in values if isinstance(v, dict) and isinstance(v.get(identity), str)], mapped

    intents, intent_map = section('service_intents', 'intent_id')
    bindings, binding_map = section('bindings', 'intent_id')
    _, artifacts = section('artifacts', 'artifact_id')
    for identity in sorted(set(intent_map) ^ set(binding_map)):
        add('saved_structure', 'intent_binding_roster_mismatch', identity)
    writers, dependencies = defaultdict(list), {i: set() for i in intent_map}
    observed_services = [b.get('service_id') for b in bindings]
    if Counter(str(s) for s in observed_services) != Counter(operations.keys()):
        add('adapter_limit', 'exact_six_service_roster_required', 'bindings')

    for index, binding in enumerate(bindings):
        intent = binding['intent_id']; subject = f'bindings/{index}:{intent}'
        service, version = binding.get('service_id'), binding.get('service_version')
        descriptor = None
        if not isinstance(service, str) or not isinstance(version, str):
            add('saved_structure', 'invalid_service_identity', subject)
        else:
            try:
                descriptor, error = catalog_get(service, version)
                if error:
                    category = 'public_catalog' if error == 'service_version_absent_from_public_catalog' else 'inspection_error'
                    add(category, error, subject)
            except Exception as exc:
                add('inspection_error', 'public_catalog_unreadable', subject, error_type=type(exc).__name__)
        services.append({'intent_id': intent, 'service_id': service, 'service_version': version,
                         'public_descriptor_available': descriptor is not None})
        if service not in operations or version != '1.0.0':
            add('adapter_limit', 'unimplemented_service_version', subject)
        if binding.get('secret_bindings'):
            add('adapter_limit', 'secret_dependent_binding', subject)

        interface = descriptor.get('interface', {}) if descriptor else {}
        for field, declarations, adapter_ports in (
            ('input_bindings', interface.get('inputs', []), {'input_artifacts'}),
            ('output_bindings', interface.get('outputs', []), {'output_artifacts', 'execution_report'}),
        ):
            raw = binding.get(field)
            if not isinstance(raw, list):
                add('saved_structure', 'bindings_not_list', subject + '/' + field)
                raw = []
            values = [v for v in raw if isinstance(v, dict) and isinstance(v.get('port'), str)
                      and isinstance(v.get('artifact_id'), str)]
            if len(values) != len(raw):
                add('saved_structure', 'malformed_port_binding', subject + '/' + field)
            seen = Counter(v['port'] for v in values)
            declared = {d['name']: d for d in declarations}
            if set(seen) != adapter_ports or any(n != 1 for n in seen.values()):
                add('adapter_limit', 'exact_port_arrangement_required', subject + '/' + field,
                    port_counts=dict(seen))
            if descriptor:
                for name, decl in declared.items():
                    if decl.get('required') is True and not seen[name]:
                        add('public_catalog', 'required_service_port_unbound', subject + '/' + field + '/' + name)
                for name, count in seen.items():
                    if name not in declared:
                        add('public_catalog', 'unknown_service_port', subject + '/' + field + '/' + name)
                    elif count > 1 and declared[name].get('cardinality') == 'one':
                        add('public_catalog', 'single_port_bound_multiple_times', subject + '/' + field + '/' + name)
            if service == 'bounded_timeseries_event_ingestor' and field == 'input_bindings' and not values:
                add('v2_input_mapping', 'ingestor_has_no_explicit_input_link', subject,
                    original_input_required=any(d.get('required') is True for d in declarations))
            for item in values:
                identity = item['artifact_id']; artifact = artifacts.get(identity)
                where = subject + '/' + field + '/' + identity
                if artifact is None:
                    add('dataflow', 'bound_artifact_undeclared', where)
                    continue
                producer = artifact.get('producer')
                producers = producer if isinstance(producer, list) else [producer] if producer else []
                if field == 'output_bindings':
                    writers[identity].append(intent)
                    if intent not in producers:
                        add('dataflow', 'bound_writer_not_declared_producer', where)
                    if artifact.get('media_type') not in (None, 'application/json') or artifact.get('data_type') not in ('any', 'json', 'object', 'table', 'status'):
                        add('adapter_limit', 'non_json_output_shape', where)
                elif producers:
                    for producer_id in producers:
                        if not isinstance(producer_id, str) or producer_id not in dependencies:
                            add('dataflow', 'unknown_artifact_producer', where)
                        elif intent in dependencies:
                            dependencies[intent].add(producer_id)
                    if isinstance(producer, list):
                        add('adapter_limit', 'producer_merge_not_implemented', where)
                else:
                    row = {'intent_id': intent, 'artifact_id': identity, 'fixture_ref': artifact.get('fixture_ref')}
                    reference = artifact.get('fixture_ref')
                    if not reference:
                        row['state'] = 'no_explicit_fixture_link'
                        add('v2_input_mapping', row['state'], where)
                    else:
                        try:
                            path = fixture_file(reference, active)
                            row['active_relative_path'] = path.relative_to(active.resolve()).as_posix()
                            if not path.is_file():
                                row['state'] = 'fixture_target_not_file'
                                add('v2_input_mapping', row['state'], where)
                            else:
                                row['state'] = 'public_file_exists'
                                if service == 'bounded_timeseries_event_ingestor':
                                    if path.stat().st_size > max_bytes:
                                        add('inspection_error', 'fixture_manifest_inspection_limit', where)
                                    else:
                                        try:
                                            manifest = load_json(path)
                                            declared_inputs = manifest.get('inputs') if isinstance(manifest, dict) else None
                                            if not isinstance(declared_inputs, dict) or not set(fixture_keys).issubset(declared_inputs):
                                                row['state'] = 'not_v2_input_manifest'
                                                add('v2_input_mapping', row['state'], where)
                                            else:
                                                row['state'] = 'v2_manifest_files_available'
                                                for key in fixture_keys:
                                                    data = safe_path(active, declared_inputs[key])
                                                    if not data.is_file():
                                                        row['state'] = 'v2_manifest_data_unavailable'
                                                        add('v2_input_mapping', row['state'], where + '/' + key)
                                        except (ValueError, TypeError, OSError):
                                            row['state'] = 'manifest_not_readable_under_v2_rules'
                                            add('v2_input_mapping', row['state'], where)
                        except (ValueError, TypeError, OSError):
                            row['state'] = 'fixture_reference_form_unmapped'
                            add('v2_input_mapping', row['state'], where)
                    inputs.append(row)

        parameters = binding.get('parameter_bindings')
        if not isinstance(parameters, dict):
            add('saved_structure', 'parameter_bindings_not_object', subject)
            parameters = {}
        declarations = {d['name']: d for d in interface.get('parameters', [])}
        if descriptor:
            for name, decl in declarations.items():
                if name not in parameters:
                    if decl.get('required') is True:
                        add('public_catalog', 'required_parameter_absent', subject + '/' + name)
                    continue
                constraint = {k: decl[k] for k in ('type', 'enum', 'minimum', 'maximum') if k in decl}
                for error in Draft202012Validator(constraint).iter_errors(parameters[name]):
                    add('public_catalog', 'parameter_constraint_violation', subject + '/' + name, validator=error.validator)
            for name in set(parameters) - set(declarations):
                add('public_catalog', 'parameter_not_in_descriptor', subject + '/' + name)
            if 'operation_profile' in declarations and 'enum' not in declarations['operation_profile']:
                add('public_semantics_unspecified', 'profile_values_not_enumerated_in_catalog', subject + '/operation_profile')
        if service in operations and parameters.get('operation_profile') != operations[service]:
            add('adapter_limit', 'exact_profile_label_required', subject + '/operation_profile')
        if set(parameters) - {'operation_profile', 'modality_policy'}:
            add('adapter_limit', 'unimplemented_parameter_semantics', subject)
        policy = parameters.get('modality_policy', {})
        if not isinstance(policy, dict) or set(policy) - {'batch', 'true_streaming'} or policy.get('true_streaming', False) is not False:
            add('adapter_limit', 'modality_policy_outside_subset', subject)

    for identity, artifact in artifacts.items():
        producer = artifact.get('producer')
        producers = producer if isinstance(producer, list) else [producer] if producer else []
        actual = writers[identity]
        if len(actual) > 1:
            declared_names = [p for p in producers if isinstance(p, str)]
            category = 'adapter_limit' if (isinstance(producer, list) and len(declared_names) == len(producers)
                and len(set(actual)) == len(actual) and set(actual) == set(declared_names)) else 'dataflow'
            add(category, 'multiple_bound_writers', identity, writer_count=len(actual))
        for producer_id in producers:
            if producer_id not in actual:
                add('dataflow', 'declared_producer_has_no_output_binding', identity)

    flow = ir.get('control_flow')
    if not isinstance(flow, dict):
        add('saved_structure', 'control_flow_not_object', 'control_flow')
        flow = {}
    if set(flow) - {'edges', 'branches', 'gates', 'parallel_groups'}:
        add('adapter_limit', 'unknown_control_semantics', 'control_flow')
    for field in ('branches', 'gates', 'parallel_groups'):
        if flow.get(field):
            add('adapter_limit', 'nonlinear_control_not_implemented', 'control_flow/' + field)
    edges = flow.get('edges', [])
    if not isinstance(edges, list):
        add('saved_structure', 'edges_not_list', 'control_flow/edges')
        edges = []
    for index, edge in enumerate(edges):
        where = 'control_flow/edges/' + str(index)
        if not isinstance(edge, dict) or not isinstance(edge.get('from'), str) or not isinstance(edge.get('to'), str):
            add('dataflow', 'malformed_control_edge', where)
            continue
        if set(edge) != {'from', 'to'}:
            add('adapter_limit', 'edge_annotations_not_implemented', where)
        if edge['from'] not in dependencies or edge['to'] not in dependencies:
            add('dataflow', 'unknown_control_endpoint', where)
        else:
            dependencies[edge['to']].add(edge['from'])
    pending, done = set(dependencies), set()
    while pending:
        ready = {i for i in pending if dependencies[i].issubset(done)}
        if not ready:
            add('dataflow', 'dependency_cycle', 'control_flow')
            break
        pending -= ready; done |= ready
    return result(findings, services, inputs)


def result(findings, services, inputs):
    return {'state': 'inspected', 'findings': findings,
            'finding_counts': dict(Counter(v['category'] for v in findings)),
            'services': services, 'external_inputs': inputs,
            'execution_ready': False, 'semantic_outcome': 'not_measured',
            'scope': 'Bounded-window static subset; not the full public G0-G6 validator.'}
