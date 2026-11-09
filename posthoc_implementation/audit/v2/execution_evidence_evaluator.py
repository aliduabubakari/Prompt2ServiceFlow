"""Correct scenario coverage for saved v1 runtimes; never claim mock semantics.

Executes only the newly compiled, pinned public-contract mock programs.
Use the original sandbox and unchanged predicate operators/expected values.
Compilation happens before this evaluator is supplied with held-out metadata.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile

import scenario_alignment_v2 as metadata
from prompt2serviceflow.validators.instance_validation import _execute_scenarios, _evaluate_assertion
import output_role_matching as roles
import audit_v2_output_trace as trace
import public_output_runtime as compiler
import execution_evidence_runtime as evidence

VERSION = 'p2sf.execution-evidence-replay/1'


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def files(root): return {p.relative_to(root).as_posix(): metadata.sha(p) for p in sorted(Path(root).rglob('*')) if p.is_file()}


def scenario_roster(runtime, assertions):
    names = [s['name'] for s in runtime['scenarios']]; reviewed = [s['scenario'] for s in assertions['scenarios']]
    if not names or len(set(names)) != len(names) or len(set(reviewed)) != len(reviewed) or set(names) != set(reviewed):
        raise ValueError('Nonempty identical unique runtime/assertion scenario rosters required')
    for s in runtime['scenarios']:
        if not isinstance(s.get('parameters'), dict): raise ValueError('Explicit reviewed parameter maps required')
    for s in assertions['scenarios']:
        checks = s.get('assertions'); ids = [a['assertion_id'] for a in checks or []]
        if not checks or len(ids) != len(set(ids)): raise ValueError('Nonempty unique assertion sets required')
        for assertion in checks: metadata.bounded.safe(Path('/snapshot-placeholder'), assertion['path'])
    return names


def score(snapshot_root, execution, definitions):
    checks = []
    for assertion in definitions:
        metadata.bounded.safe(snapshot_root, assertion['path'])
        if execution['_errors']:
            status, message = 'unscored_execution_error', 'Recorded task execution did not complete'
        else:
            try:
                ok, message = _evaluate_assertion(assertion, snapshot_root); status = 'pass' if ok else 'fail'
            except (json.JSONDecodeError,UnicodeDecodeError) as exc:
                status,message='fail','output_format_error: '+type(exc).__name__+': '+str(exc)[:500]
            except (KeyError,IndexError) as exc:
                status,message='fail','missing_output_field: '+str(exc)[:500]
            except TypeError as exc:
                status,message='fail','output_value_type_error: '+str(exc)[:500]
            except Exception as exc: status, message = 'evaluation_error', type(exc).__name__ + ': ' + str(exc)[:500]
        checks.append({'assertion_id': assertion['assertion_id'], 'status': status, 'message': message})
    return {'scenario': execution['scenario'], 'execution_errors': execution['_errors'], 'assertions': checks,
            'reviewed_assertion_pass': bool(checks) and not execution['_errors'] and all(c['status'] == 'pass' for c in checks)}


def complete(names, reports):
    observed = [r['scenario'] for r in reports]
    return bool(names) and len(names) == len(set(names)) and len(observed) == len(set(observed)) and set(names) == set(observed)


def replay(submission, instance, output, identity, *, writer_plan, public_fixture_root, public_fixture_inventory, timeout=30):
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    source_runtime = metadata.document(Path(submission) / 'runtime/manifest.yaml')
    reviewed = metadata.document(Path(instance) / 'runtime/manifest.yaml'); assertions = metadata.document(Path(instance) / 'gold/assertions.yaml')
    names = scenario_roster(reviewed, assertions); definitions = {s['scenario']: s['assertions'] for s in assertions['scenarios']}
    overridden = copy.deepcopy(source_runtime); overridden['scenarios'] = copy.deepcopy(reviewed['scenarios'])
    # Supply complete reviewed inputs to the evaluator only. Retain source task
    # invocations verbatim: a program ignoring parameters must not be repaired.
    write(output / 'original_runtime.json', source_runtime); write(output / 'evaluation_runtime.json', overridden)
    write(output / 'unchanged_assertions.json', assertions)
    contexts = metadata.scenario_contexts(instance, reviewed)
    mapping_file = Path(instance) / 'gold/artifact_mappings.yaml'
    reference_file = Path(instance) / 'gold/serviceflow.yaml'
    mappings = metadata.document(mapping_file) if mapping_file.is_file() else {'mappings': []}
    reference = metadata.document(reference_file) if reference_file.is_file() else {'bindings': [], 'service_intents': []}
    source_ir_file = Path(submission) / 'serviceflow.yaml'
    submitted = metadata.document(source_ir_file) if source_ir_file.is_file() else {'bindings': [], 'service_intents': []}
    write(output / 'reviewed_input_provenance.json', contexts)
    visible = {name: metadata.sha(metadata.bounded.safe(Path(public_fixture_root), name)) for name in public_fixture_inventory}
    if visible != public_fixture_inventory: raise ValueError('Public fixture inventory changed')
    write(output / 'public_visible_fixtures.json', visible)
    with tempfile.TemporaryDirectory(prefix='p2sf-corpus-replay-') as temporary:
        virtual = Path(temporary) / 'instance'; virtual.mkdir()
        shutil.copytree(Path(submission) / 'runtime', virtual / 'runtime')
        (virtual / 'fixtures').mkdir()
        for relative in visible:
            destination = metadata.bounded.safe(virtual / 'fixtures', relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(metadata.bounded.safe(Path(public_fixture_root), relative), destination)
        for scenario in reviewed['scenarios']:
            selected, _ = metadata.fixture_root(virtual, scenario)
            selected.mkdir(parents=True, exist_ok=True)
        executions = _execute_scenarios(virtual, overridden, sandbox_generated=True, task_timeout_seconds=timeout)
    reports = []
    for index, execution in enumerate(executions):
        directory = output / 'scenarios' / execution['scenario']; snapshot = directory / 'snapshot'; snapshot.mkdir(parents=True)
        payload = execution['_snapshot']
        if len(payload) > 10000 or sum(len(v) for v in payload.values()) > 67108864: raise ValueError('Snapshot retention limit exceeded')
        for relative, data in payload.items():
            path = metadata.bounded.safe(snapshot, relative); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        provenance = {'cell_id': identity, 'scenario': execution['scenario'], 'parameters': contexts[execution['scenario']]['parameters'],
            'fixture_context': contexts[execution['scenario']], 'executed_tasks': execution['executed_tasks'],
            'skipped_tasks': execution['skipped_tasks'], 'execution_errors': execution['_errors'],
            'source_runtime_sha256': metadata.sha(Path(submission) / 'runtime/manifest.yaml'),
            'runtime_kind': 'file_backed_execution_evidence_v1', 'business_semantics_verified': False}
        write(directory / 'execution_provenance.json', provenance)
        manifest = files(snapshot); write(directory / 'snapshot_manifest.json', {'files': manifest, 'snapshot_role': 'actual saved-runtime outputs before predicate evaluation'})
        # Only now may the unchanged reviewed predicates inspect saved bytes.
        checked = score(snapshot, execution, definitions[execution['scenario']])
        associated = []
        for definition in definitions[execution['scenario']]:
            association = roles.associated_path(definition, reference, mappings, submitted, writer_plan)
            selected = roles.predicate_copy(definition, association)
            if selected is None:
                outcome = {'assertion_id': definition['assertion_id'], 'status': 'unscored_role_unresolved', 'message': association['state']}
            else:
                outcome = score(snapshot, execution, [selected])['assertions'][0]
            associated.append({**outcome, 'original_path': definition['path'], 'path_association': association})
        checked['role_matched_assertions'] = associated
        checked['role_matched_assertion_pass'] = bool(associated) and not execution['_errors'] and all(c['status'] == 'pass' for c in associated)
        write(directory / 'score.json', checked)
        if files(snapshot) != manifest: raise ValueError('Scoring modified the output snapshot')
        reports.append(checked)
    coverage = complete(names, reports)
    return {'state': 'replayed', 'runtime_kind': 'file_backed_execution_evidence_v1', 'business_semantics_verified': False,
        'required_scenarios': names, 'complete_scenario_coverage': coverage, 'scenarios': reports,
        'execution_errors': sum(bool(r['execution_errors']) for r in reports),
        'reviewed_assertion_pass': coverage and all(r['reviewed_assertion_pass'] for r in reports),
        'role_matched_assertion_pass': coverage and all(r['role_matched_assertion_pass'] for r in reports),
        'scope': 'Paired literal-path and output-role checks under the public file-backed execution-evidence mock profile. This is not a verified real-business semantic score or an unchanged v1 end-to-end result.'}
