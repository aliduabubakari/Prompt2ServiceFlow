"""Frozen, explicit-resource admission and read-only business-result checks.

No model-specific or pipeline-specific repair rules. This module does not call
an LLM, execute generated programs, or edit the verified projection adapter.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import csv_ir_adapter as adapter
import csv_postgres_oracle as oracle
import csv_replay_eligibility as public


class Refusal(ValueError):
    def __init__(self, category, code, message):
        super().__init__(message); self.category, self.code = category, code


def need(condition, category, code, message):
    if not condition: raise Refusal(category, code, message)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def original_target(ir, default_schema):
    loaders = [b for b in ir['bindings'] if b.get('service_id') in (adapter.SNAPSHOT, adapter.TABULAR)]
    need(len(loaders) == 1, 'backend_subset', 'unsupported_loader_roster', 'Exactly one registered loader must already be bound')
    binding = loaders[0]; p = binding['parameter_bindings']
    name = p['import_spec']['target_table'] if binding['service_id'] == adapter.SNAPSHOT else p['target_table']
    schema, table = adapter.target_name(name, default_schema)
    need(schema != 'information_schema' and not schema.startswith('pg_'), 'backend_subset', 'reserved_target_schema', 'System schemas are outside the isolated target contract')
    return {'schema': schema, 'table': table, 'logical_name': name, 'loader_service': binding['service_id'],
            'write_mode': p['load_mode'] if binding['service_id'] == adapter.SNAPSHOT else p['write_mode']}


def assemble(ir, context, design):
    """Build a separate intervention from explicit public links, never guesses."""
    workspace = Path(context['workspace']); expected = public.safe(workspace, context['source_csv'])
    raw = expected.read_bytes(); header, _ = oracle.expected_csv(raw)
    # Parameters must be in the already controlled subset before a target or
    # resource is interpreted. No unsupported option is removed to obtain it.
    for b in ir['bindings']:
        need(b.get('service_id') in public.PORTS, 'backend_subset', 'unregistered_service', 'Service is outside the verified adapter')
        adapter.parameters(b['service_id'], b.get('parameter_bindings'))
    artifacts = {a['artifact_id']: a for a in ir['artifacts']}
    roles = {a: set() for a in artifacts}
    for b in ir['bindings']:
        for link in b.get('input_bindings', []):
            aid = link['artifact_id']
            need(aid in artifacts, 'saved_structure', 'undeclared_input_artifact', str(aid))
            role = 'csv' if link['port'] in ('csv_file', 'csv_snapshot') else (
                'filesystem' if b['service_id'] == adapter.SENSOR and link['port'] == 'file_location_resource' else
                'database' if b['service_id'] in (adapter.SNAPSHOT, adapter.TABULAR) and link['port'] == 'target_database' else 'produced')
            roles[aid].add(role)
    fixtures, sources = {}, {}
    for aid, a in artifacts.items():
        if a.get('producer') is not None: continue
        need(roles[aid] and len(roles[aid]) == 1 and 'produced' not in roles[aid], 'backend_subset', 'unsupported_external_role', aid)
        ref = a.get('fixture_ref')
        need(isinstance(ref, str) and ref, 'public_input_context', 'missing_fixture_link', aid)
        path, error = public.fixture(workspace, a)
        need(error is None, 'public_input_context', error or 'unresolved_fixture', aid)
        kind = next(iter(roles[aid])); data = path.read_bytes()
        entry = {'kind': kind, 'path': 'files/' + sha(ref.encode()) + ('.csv' if kind == 'csv' else '.json'),
                 'sha256': sha(data), 'original_public_path': str(path)}
        if kind == 'csv':
            need(path.resolve() == expected.resolve(), 'public_input_context', 'outside_declared_csv_source', aid)
        else:
            try: descriptor = json.loads(data)
            except (ValueError, UnicodeError) as exc: raise Refusal('public_input_context', 'invalid_resource_json', aid) from exc
            need(isinstance(descriptor, dict) and descriptor.get('driver') == 'filesystem-mock', 'runtime_intervention', 'unsupported_source_resource', aid)
            if kind == 'filesystem':
                need(set(descriptor) <= {'driver', 'path', 'filename_pattern'} and isinstance(descriptor.get('path'), str),
                     'runtime_intervention', 'unmapped_filesystem_resource', aid)
                adapter.kernels.logical_path(descriptor['path'])
                entry.update(logical_root=descriptor['path'], files={})
            else:
                need(set(descriptor) <= {'driver', 'engine', 'target', 'schema'} and descriptor.get('engine') == 'postgresql',
                     'runtime_intervention', 'unmapped_database_resource', aid)
                default = descriptor.get('schema', design['database_default_schema']); adapter.ops.ident(default)
                target = original_target(ir, default)
                entry.update(resource={'driver': adapter.ops.VERSION, 'engine': 'postgresql', 'database': 'p2sf_controls', 'schema': default},
                             allowed_schemas=[target['schema']])
        if ref in fixtures:
            need(fixtures[ref] == entry, 'saved_structure', 'conflicting_fixture_roles', ref)
        fixtures[ref] = entry; sources[ref] = str(path)
    csv_refs = sorted(ref for ref, entry in fixtures.items() if entry['kind'] == 'csv')
    need(csv_refs, 'public_input_context', 'no_explicit_csv_source', 'Do not fill a missing CSV binding')
    # The physical public file has one unchanged filename. Aliases must resolve
    # to the same explicit path; none is selected from a model's glob or date.
    for entry in fixtures.values():
        if entry['kind'] == 'filesystem': entry['files'] = {expected.name: csv_refs[0]}
    databases = [e for e in fixtures.values() if e['kind'] == 'database']
    need(len(databases) == 1, 'runtime_intervention', 'unsupported_database_resources', 'One explicit database resource is required')
    target = original_target(ir, databases[0]['resource']['schema'])
    validators = [b for b in ir['bindings'] if b['service_id'] == adapter.CSV]
    need(len(validators) == 1, 'backend_subset', 'unsupported_validator_roster', 'Require one validator')
    required = validators[0]['parameter_bindings']['required_columns']
    need(set(required) <= set(header), 'public_input_context', 'required_columns_absent_from_public_csv', 'Saved validation columns do not match the unchanged public CSV')
    if target['loader_service'] == adapter.SNAPSHOT:
        p = next(b['parameter_bindings'] for b in ir['bindings'] if b['service_id'] == adapter.SNAPSHOT)
        need('columns' not in p['import_spec'] or p['import_spec']['columns'] == header,
             'backend_subset', 'nonidentity_columns', 'Keep the declared column list; no reordering or mapping is inferred')
    intervention = {'version': adapter.VERSION, 'execution': 'single_attempt_reference',
        'accepted_source_profiles': design['accepted_source_profiles'], 'fixtures': fixtures,
        'scope': design['intervention_scope'], 'database_default_schema_policy': design['database_default_schema_policy']}
    schemas = {}
    for a in ir['artifacts']:
        if a.get('producer') is None: continue
        ref = a.get('schema_ref')
        need(isinstance(ref, str) and ref, 'public_input_context', 'missing_output_schema', a['artifact_id'])
        path = public.safe(workspace, ref)
        need(path.is_file(), 'public_input_context', 'original_output_schema_unavailable', ref)
        schema = json.loads(path.read_text()); adapter.checked_schema(schema); schemas[ref] = schema
    plan = adapter.compile_projection(ir, intervention, schemas)
    return {'plan': plan, 'fixture_sources': sources, 'target': target, 'required_columns': required,
            'source_csv': str(expected), 'source_csv_sha256': sha(raw)}


def inspect(source, context, design):
    path = Path(source['artifact']); raw_sha = sha(path.read_bytes()) if path.is_file() else 'MISSING'
    row = {'source': source, 'artifact_sha256': raw_sha, 'state': 'blocked', 'findings': [], 'semantic_outcome': 'not_measured'}
    documents, error = public.read_saved(path, design['max_document_bytes'], design['max_document_nodes'])
    if error:
        row.update(state='missing' if error == 'missing_saved_artifact' else 'blocked', findings=[{'category': 'saved_structure', 'code': error}]); return row
    if len(documents) != 1 or not isinstance(documents[0], dict):
        row['findings'] = [{'category': 'saved_structure', 'code': 'not_one_ir_document'}]; return row
    ir = documents[0]
    errors = list(Draft202012Validator(context['schema']).iter_errors(ir))
    if errors:
        row['findings'] = [{'category': 'saved_structure', 'code': 'full_ir_schema_error',
                            'path': list(e.absolute_path), 'validator': e.validator} for e in errors[:100]]
        row['full_ir_schema_error_count'] = len(errors); return row
    row['full_ir_schema_valid'] = True
    try:
        row.update(assemble(ir, context, design)); row['state'] = 'admitted'
    except Refusal as exc: row['findings'] = [{'category': exc.category, 'code': exc.code, 'message': str(exc)}]
    except adapter.Error as exc: row['findings'] = [{'category': 'adapter_subset', 'code': exc.code, 'message': str(exc)}]
    except (ValueError, TypeError, KeyError, adapter.kernels.UnsupportedOperation) as exc:
        row['findings'] = [{'category': 'adapter_subset', 'code': 'unsupported_or_malformed_projection', 'exception': type(exc).__name__, 'message': str(exc)[:400]}]
    return row


def variant(raw, name, required):
    import csv
    import io
    header, rows = oracle.expected_csv(raw)
    if name == 'missing_file': return None
    if name == 'changed_value': rows[0][-1] += '__changed__'
    elif name == 'extra_row': rows.append(list(rows[0]))
    elif name == 'missing_required_column':
        index = header.index(required[0]); header.pop(index)
        for r in rows: r.pop(index)
    elif name != 'nominal': raise ValueError('Undeclared replay trial')
    stream = io.StringIO(newline=''); csv.writer(stream, lineterminator='\n').writerows([header, *rows])
    return raw if name == 'nominal' else stream.getvalue().encode()


def materialize(row, directory, scenario):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=False)
    plan = copy.deepcopy(row['plan']); original = Path(row['source_csv']).read_bytes()
    need(sha(original) == row['source_csv_sha256'], 'integrity', 'source_csv_changed', 'Public source CSV changed')
    raw = variant(original, scenario, row['required_columns'])
    for ref, entry in plan['intervention']['fixtures'].items():
        source = Path(row['fixture_sources'][ref]); data = source.read_bytes()
        need(sha(data) == entry['sha256'], 'integrity', 'public_fixture_changed', ref)
        target = adapter.ops.inside(directory, entry['path']); target.parent.mkdir(parents=True, exist_ok=True)
        if entry['kind'] == 'csv':
            entry['sha256'] = sha(raw) if raw is not None else 'MISSING'
            if raw is not None: target.write_bytes(raw)
        else: target.write_bytes(data)
    # Each probe changes declared fixture bytes only, with a new hashed plan.
    # The preserved source IR, schemas and every model choice are identical.
    plan = adapter.compile_projection(plan['source_ir'], plan['intervention'], plan['schemas'])
    return plan, raw


def evaluate(scenario, raw, receipt, failure, before, after):
    if scenario in ('nominal', 'changed_value', 'extra_row'):
        checks = oracle.check_loaded(after, raw, (receipt or {}).get('load_status') or {})['checks']
        checks.update(no_execution_error=failure is None, loaded=(receipt or {}).get('state') == 'loaded',
                      actual_output_count=((receipt or {}).get('load_status') or {}).get('rows_loaded') == len(oracle.expected_csv(raw)[1]))
    elif scenario == 'missing_file':
        checks = {'no_execution_error': failure is None, 'gate_skipped': (receipt or {}).get('state') == 'skipped_missing_input',
                  'loader_not_called': (receipt or {}).get('loader_called') is False, 'no_database_change': oracle.same_state(before, after)}
    elif scenario == 'missing_required_column':
        checks = {'expected_validation_refusal': (failure or {}).get('code') == 'csv_validation_failed',
                  'no_database_change': oracle.same_state(before, after)}
    else: raise ValueError('Undeclared evaluation trial')
    return {'pass': all(checks.values()), 'checks': checks}
