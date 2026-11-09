#!/usr/bin/env python3
"""Trace known retained mock writers statically; never import model scripts."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import audit_v2_failure_attribution as attribution
from prompt2serviceflow.experiments import runtime_compiler
from prompt2serviceflow.validators.instance_validation import _json_path

generation = attribution.generation
controls, replay, parent = attribution.controls, attribution.replay, attribution.parent
CONFIG = ROOT / 'audit/v2/output_trace.json'
TESTS = ROOT / 'tests/unit/test_v2_output_trace.py'
FILES = [Path(__file__).resolve(), CONFIG, TESTS, ROOT / 'audit/v2/OUTPUT_TRACE.md',
         ROOT / 'src/prompt2serviceflow/experiments/runtime_compiler.py',
         ROOT / 'src/prompt2serviceflow/validators/instance_validation.py']


def local(root, relative):
    if (not isinstance(relative, str) or not relative or Path(relative).is_absolute()
            or '..' in Path(relative).parts or '://' in relative):
        raise ValueError('Only contained relative paths allowed')
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Path escaped its source directory')
    return path


def recognize(text):
    """Parse literal metadata and require AST equality with the frozen renderer."""
    try:
        tree = ast.parse(text)
        assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                       and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                       and node.targets[0].id == 'OUTPUTS']
        if len(assignments) != 1:
            return None
        value = assignments[0].value
        if not (isinstance(value, ast.Call) and len(value.args) == 1 and not value.keywords
                and isinstance(value.func, ast.Attribute) and value.func.attr == 'loads'
                and isinstance(value.func.value, ast.Name) and value.func.value.id == 'json'
                and isinstance(value.args[0], ast.Constant) and isinstance(value.args[0].value, str)):
            return None
        outputs = generation.compact_ir.strict_json(value.args[0].value)
        if not isinstance(outputs, list) or len(outputs) > 10000:
            return None
        if any(not isinstance(o, dict) or not isinstance(o.get('artifact_id'), str)
               or not re.fullmatch(r'[a-z][a-z0-9_]*', o['artifact_id'])
               or not isinstance(o.get('data_type'), str) for o in outputs):
            return None
        canonical = ast.parse(runtime_compiler._script_text(outputs))
        if ast.dump(tree, include_attributes=False) != ast.dump(canonical, include_attributes=False):
            return None
        return outputs
    except (SyntaxError, ValueError, TypeError, RecursionError):
        return None


def planned_output(spec):
    identity = spec['artifact_id']
    if spec.get('json_value') is not None:
        return {'artifact_id': identity, 'path': f'artifacts/{identity}.json',
                'kind': 'literal_json', 'literal_json_value': spec['json_value']}
    if spec['data_type'] in ('csv', 'table'):
        return {'artifact_id': identity, 'path': f'artifacts/{identity}.csv', 'kind': 'first_csv_copy_or_header'}
    if spec['data_type'] in ('binary', 'image') or spec.get('media_type') == 'application/pdf':
        suffix = '.pdf' if spec.get('media_type') == 'application/pdf' else '.bin'
        return {'artifact_id': identity, 'path': f'artifacts/{identity}{suffix}', 'kind': 'fixed_mock_bytes'}
    suffix = '.md' if spec['data_type'] == 'markdown' else '.txt'
    return {'artifact_id': identity, 'path': f'artifacts/{identity}{suffix}', 'kind': 'fixed_example_text'}


def scan_runtime(submission, runtime, max_bytes):
    scripts, writers = [], []
    tasks = runtime.get('tasks') or []
    for task in tasks:
        record = {'intent_id': task.get('intent_id'), 'script': task.get('script'), 'state': 'unrecognized'}
        try:
            path = local(submission / 'runtime', task['script'])
            if not path.is_file():
                record['state'] = 'missing_script'
            elif path.stat().st_size > max_bytes:
                record['state'] = 'script_size_limit'
            elif (task.get('arguments') != ['--workspace', '{workspace}', '--fixtures', '{fixtures}']
                  or set(task) - {'intent_id', 'script', 'arguments', 'retries', 'dependencies'}):
                record['state'] = 'unrecognized_task_invocation'
            else:
                outputs = recognize(path.read_text())
                if outputs is not None:
                    record['state'] = 'recognized_frozen_mock'
                    record['outputs'] = outputs
                    writers.extend({**planned_output(spec), 'intent_id': task['intent_id']} for spec in outputs)
        except (ValueError, TypeError, KeyError, OSError) as exc:
            record['state'] = 'unresolved_script'
            record['error_type'] = type(exc).__name__
        scripts.append(record)
    return {'scripts': scripts, 'writers': writers,
            'complete_recognized_writer_plan': bool(tasks) and all(s['state'] == 'recognized_frozen_mock' for s in scripts),
            'scope': 'Possible writers from retained recognized code, not an execution snapshot or proof of task semantics.'}


def private_roles(mappings, artifact_id):
    result = []
    for row in mappings.get('mappings', []):
        for port, value in row.get('outputs', {}).items():
            ids = [value] if isinstance(value, str) else value if isinstance(value, list) else []
            if artifact_id in ids:
                result.append({'intent_id': row['intent_id'], 'port': port})
    return result


def trace_predicate(definition, check, plan, ir, mappings):
    relative = definition['path']
    exact = [writer for writer in plan['writers'] if writer['path'] == relative]
    stem = Path(relative).stem
    roles = private_roles(mappings, stem)
    counterpart_ids = sorted({port['artifact_id'] for role in roles for binding in ir.get('bindings', [])
        if binding.get('intent_id') == role['intent_id'] for port in binding.get('output_bindings', [])
        if port.get('port') == role['port']})
    declared = {artifact['artifact_id'] for artifact in ir.get('artifacts', [])}
    same_id = [writer for writer in plan['writers'] if writer['artifact_id'] == stem]
    if len(exact) > 1:
        relation = 'multiple_recognized_writers_same_path'
    elif exact:
        relation = 'exact_recognized_planned_path'
    elif not plan['complete_recognized_writer_plan']:
        relation = 'unresolved_due_to_incomplete_writer_recognition'
    elif not relative.startswith('artifacts/'):
        relation = 'outside_recognized_artifact_namespace'
    elif same_id:
        relation = 'same_artifact_id_different_suffix'
    elif counterpart_ids:
        relation = 'reference_role_bound_under_other_artifact_ids'
    elif stem in declared:
        relation = 'declared_ir_artifact_not_in_recognized_outputs'
    else:
        relation = 'no_matching_recognized_writer'
    result = {'assertion_id': definition['assertion_id'], 'type': definition['type'], 'path': relative,
              'json_path': definition.get('json_path'), 'recorded_status': check.get('status'),
              'recorded_message_category': attribution.message_category(check), 'path_relation': relation,
              'private_reference_roles': roles, 'model_role_bound_artifact_ids': counterpart_ids,
              'same_id_planned_paths': sorted({writer['path'] for writer in same_id}),
              'exact_writer_kinds': [writer['kind'] for writer in exact]}
    if len(exact) == 1 and exact[0]['kind'] == 'literal_json' and definition.get('json_path') is not None:
        try:
            result['literal_json_field_value'] = _json_path(exact[0]['literal_json_value'], definition['json_path'])
            result['literal_json_field_state'] = 'present'
        except (KeyError, IndexError, TypeError, ValueError):
            result['literal_json_field_state'] = 'absent_or_incompatible'
    return result


def get_report(record, posthoc):
    if record['assertion_evidence_source'] == 'published_main_posthoc':
        model, method, split, case, sample = record['id'].split('/')
        return posthoc['results']['/'.join((model, 'primary', method, split, case, sample))].get('g6_assert') or {}
    score = replay.read_json(Path(record['score_path']))
    return score.get('g6_assert') or {}


def inspect_record(record, posthoc, design):
    submission = Path(record['saved_ir_path']).parent
    ir = controls.load(Path(record['saved_ir_path']))
    runtime_path = submission / 'runtime/manifest.yaml'
    runtime = controls.load(runtime_path) if runtime_path.is_file() else {}
    plan = scan_runtime(submission, runtime, design['max_script_bytes'])
    original_score, _ = attribution.read_optional_json(Path(record['score_path']))
    agreement = bool((original_score or {}).get('submission')) and Path(original_score['submission']).resolve() == submission.resolve()
    if not agreement:
        plan['complete_recognized_writer_plan'] = False
    instance = controls.BENCHMARK / 'instances' / record['case']
    assertions = controls.load(instance / 'gold/assertions.yaml')
    mapping_file = instance / 'gold/artifact_mappings.yaml'
    try:
        mappings = controls.load(mapping_file) if mapping_file.is_file() else {}
        if not isinstance(mappings, dict) or not isinstance(mappings.get('mappings', []), list):
            raise ValueError('Unsupported private mapping shape')
        mapping_state = 'present' if mapping_file.is_file() else 'missing'
    except (ValueError, TypeError, OSError, controls.yaml.YAMLError):
        mappings, mapping_state = {}, 'unresolved_mapping'
    definitions = {(s['scenario'], a['assertion_id']): a for s in assertions['scenarios'] for a in s['assertions']}
    report = get_report(record, posthoc)
    traces = []
    for scenario in report.get('scenarios', []):
        actual = scenario['scenario']
        reviewed = scenario.get('assertion_scenario') or report.get('scenario_aliases', {}).get(actual, actual)
        for check in scenario.get('assertions', []):
            definition = definitions.get((reviewed, check['assertion_id']))
            if definition is None:
                traces.append({'assertion_id': check['assertion_id'], 'path_relation': 'unmatched_assertion_definition',
                               'recorded_status': check.get('status'), 'recorded_message_category': attribution.message_category(check)})
            else:
                traces.append({**trace_predicate(definition, check, plan, ir, mappings), 'scenario': actual, 'assertion_scenario': reviewed})
    return {'id': record['id'], 'model': record['model'], 'method': record['method'], 'case': record['case'],
            'published_semantic_success': record['published_semantic_success'],
            'recorded_stage_category': record['recorded_stage_category'], 'retained_submission_path_agrees_with_score': agreement,
            'private_mapping_state': mapping_state,
            'writer_plan': plan, 'assertion_traces': traces,
            'retained_runtime_scenario_names': [s['name'] for s in runtime.get('scenarios', [])],
            'reviewed_assertion_scenario_names': [s['scenario'] for s in assertions['scenarios']],
            'recorded_scenario_aliases': report.get('scenario_aliases', {}),
            'recorded_unmatched_assertion_scenarios': report.get('unmatched_assertion_scenarios', []),
            'recorded_unmatched_execution_scenarios': report.get('unmatched_execution_scenarios', []),
            'scope': 'Static retained-code evidence, not newly observed outputs or corrected scores.'}


def prepare():
    design = replay.read_json(CONFIG)
    if design['maximum_inference_requests'] != 0:
        raise ValueError('No inference permitted')
    root = ROOT / design['parent_attribution']
    previous = replay.read_json(root / 'run.json')
    if previous['status'] != 'complete' or previous.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged attribution ledger required')
    hashes = parent.verify_hashes(root, previous)
    generation.verify_completed(previous)
    ledger = replay.read_json(root / 'evidence/cells.json')
    if len(ledger) != design['expected_original_cells'] or len({r['id'] for r in ledger}) != len(ledger):
        raise ValueError('Original attribution roster changed')
    selected = [r for r in ledger if r.get('published_executable_valid') is True]
    if len(selected) != design['expected_public_valid_cells']:
        raise ValueError('Original public-valid roster changed')
    analysis_root = Path(replay.read_json(attribution.CONFIG)['publication_analysis'])
    posthoc_path = analysis_root / 'posthoc_main_g6_assert.json'
    posthoc = replay.read_json(posthoc_path)
    paths = [*FILES, root / 'run.json', root / 'input_sha256.json', posthoc_path]
    for saved in previous['result_files'].values():
        paths.extend(Path(saved['path']).parent / name for name in saved['files'])
    for record in selected:
        submission = Path(record['saved_ir_path']).parent
        runtime_path = submission / 'runtime/manifest.yaml'
        paths.extend([Path(record['saved_ir_path']), Path(record['score_path']), runtime_path])
        if runtime_path.is_file():
            try:
                runtime = controls.load(runtime_path)
                if not isinstance(runtime, dict):
                    runtime = {}
            except (ValueError, TypeError, OSError, controls.yaml.YAMLError):
                runtime = {}
            for task in runtime.get('tasks', []):
                try:
                    paths.append(local(submission / 'runtime', task['script']))
                except (ValueError, TypeError, KeyError):
                    # The manifest is pinned; do not follow unsafe paths.
                    # Inspection retains these tasks as unrecognized evidence.
                    continue
        instance = controls.BENCHMARK / 'instances' / record['case']
        paths.extend(instance / name for name in ('gold/assertions.yaml', 'gold/artifact_mappings.yaml'))
    for path in paths:
        name = str(path.resolve())
        digest = controls.sha256(path) if path.is_file() else 'MISSING'
        if name in hashes and hashes[name] != digest:
            raise ValueError('Pinned evidence changed')
        hashes[name] = digest
    return design, selected, posthoc, hashes


def summarize(records):
    checks = [t for r in records for t in r.get('assertion_traces', [])]
    missing = [t for t in checks if t['recorded_message_category'] == 'missing_or_empty_output_message']
    return {'selected_cells': len(records), 'inspection_errors': sum('inspection_error' in r for r in records),
            'cells_with_recorded_scenario_mismatch': sum(bool(r.get('recorded_unmatched_assertion_scenarios') or r.get('recorded_unmatched_execution_scenarios')) for r in records),
            'fully_recognized_cells': sum(r.get('writer_plan', {}).get('complete_recognized_writer_plan') is True for r in records),
            'script_states': dict(Counter(s['state'] for r in records for s in r.get('writer_plan', {}).get('scripts', []))),
            'writer_kinds': dict(Counter(w['kind'] for r in records for w in r.get('writer_plan', {}).get('writers', []))),
            'observed_assertion_trace_count': len(checks), 'missing_message_path_relations': dict(Counter(t['path_relation'] for t in missing)),
            'literal_json_field_states': dict(Counter(t['literal_json_field_state'] for t in checks if 'literal_json_field_state' in t)),
            'note': 'Counts of planned writers and recorded predicates, not new model outcomes. Unknown code and unobserved scenarios remain unresolved.'}


def render(run, result):
    lines = ['# Retained runtime/output trace (static only)', '',
        f"Protocol {run['audit_protocol_version']}; state {run['status']}; original public-valid cells: {result['selected_cells']}.",
        'Includes original passes and failures. Zero model calls, workflow execution, or rescoring.', '',
        f"Fully recognized writer-plan cells: {result['fully_recognized_cells']}.",
        f"Inspection errors retained: {result['inspection_errors']}.",
        f"Cells with recorded scenario mismatch: {result['cells_with_recorded_scenario_mismatch']}.",
        '', '## Retained script states', '']
    lines.extend(f'- {key}: {value}' for key, value in sorted(result['script_states'].items()))
    lines += ['', '## Planned writer kinds (not executed output counts)', '']
    lines.extend(f'- {key}: {value}' for key, value in sorted(result['writer_kinds'].items()))
    lines += ['', '## Recorded missing/empty-output messages: static path relationships', '']
    lines.extend(f'- {key}: {value}' for key, value in sorted(result['missing_message_path_relations'].items()))
    lines += ['', '## Interpretation limits', '',
        'Only scripts AST-equivalent to the frozen deterministic mock renderer receive writer predictions. All other code remains unresolved.',
        'Literal JSON, fixture copying, and fixed example writers do not establish the advertised business operation; copying may nevertheless be appropriate for some tasks.',
        'A different suffix or reference-role name is evidence of a static contract/path discrepancy, not proof that renaming alone would make an output correct.',
        'Private artifact mappings are evaluator-only diagnostics, never repair instructions. No alias, filename, JSON value, scenario, or score is changed.',
        'Retained scripts are not execution snapshots. Scenario skips, unavailable code, and unknown historical changes limit causal conclusions.',
        'Full trace details retain scenario alignment and literal-field availability without evaluating expected values.',
        'Original outputs, published v1 scores, submitted paper, and deposit remain unchanged.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    print('Verifying original public-valid cells and retained runtime sources (offline)...', flush=True)
    design, selected, posthoc, hashes = prepare()
    if args.dry_run:
        print(json.dumps({'original_public_valid_cells': len(selected), 'includes_published_passes': True,
                          'verified_inputs': len(hashes), 'api_requests': 0, 'workflow_executions': 0,
                          'rescoring': False, 'model_scripts_imported_or_executed': False}, indent=2))
        return 0
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = ROOT / 'audit/evaluator_only' / f'package_v2_output_trace__{stamp}__{uuid.uuid4().hex[:8]}'
    output.mkdir(parents=True, exist_ok=False)
    run = {'package_version': design['package_version'], 'audit_protocol_version': design['audit_protocol_version'],
           'design': design, 'input_fingerprint': controls.fingerprint(hashes), 'environment': controls.environment(),
           'status': 'running', 'result_files': {}, 'evidence_role': 'evaluator_only_never_model_context'}
    controls.write_json(output / 'input_sha256.json', hashes)
    controls.write_json(output / 'run.json', run)
    for path in FILES:
        target = output / 'implementation' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    print('Output: ' + str(output), flush=True)
    tests = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TESTS)], cwd=ROOT,
                           capture_output=True, text=True, timeout=60)
    (output / 'verification.txt').write_text(tests.stdout + tests.stderr)
    if tests.returncode:
        run['status'] = 'verification_failed'
        controls.write_json(output / 'run.json', run)
        print('verification_failed: ' + str(output / 'verification.txt'), flush=True)
        return 1
    parent.verify_hashes(output, run)
    records = []
    for record in selected:
        try:
            trace = inspect_record(record, posthoc, design)
        except Exception as exc:
            trace = {'id': record['id'], 'model': record['model'], 'method': record['method'], 'case': record['case'],
                     'inspection_error': type(exc).__name__, 'error_message': str(exc)}
        records.append(trace)
    result = summarize(records)
    evidence = output / 'evidence'
    controls.write_json(evidence / 'cells.json', records)
    controls.write_json(evidence / 'result.json', result)
    run['result_files']['output_trace'] = generation.output_checkpoint(evidence)
    try:
        parent.verify_hashes(output, run)
        generation.verify_completed(run)
        unchanged = True
    except ValueError as exc:
        unchanged = False
        run['integrity_error'] = str(exc)
    run['source_inputs_unchanged'] = unchanged
    run['status'] = 'inputs_changed' if not unchanged else 'complete_with_errors' if result['inspection_errors'] else 'complete'
    controls.write_json(output / 'run.json', run)
    (output / 'summary.md').write_text(render(run, result))
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
