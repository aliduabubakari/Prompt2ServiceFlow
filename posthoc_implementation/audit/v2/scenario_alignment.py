"""Evaluator-only scenario provenance inspection. Never run or rescore code."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import csv_replay_eligibility as bounded


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def document(path):
    docs, error = bounded.read_saved(path)
    if error or len(docs) != 1 or not isinstance(docs[0], dict):
        raise ValueError('Unsupported metadata document: ' + str(error or path))
    return docs[0]


def tree(directory, max_files=1000, max_bytes=67108864):
    """Exact fixture-tree fingerprint; no ignored wrapper files or basenames."""
    directory = Path(directory)
    if not directory.is_dir(): return {'state': 'missing', 'files': {}}
    files = {}; total = 0
    for path in sorted(directory.rglob('*')):
        if path.is_symlink(): raise ValueError('Symlink in evidence tree')
        if not path.is_file(): continue
        relative = path.relative_to(directory).as_posix()
        bounded.safe(directory, relative)
        total += path.stat().st_size
        if len(files) >= max_files or total > max_bytes: raise ValueError('Evidence inventory limit exceeded')
        files[relative] = sha(path)
    return {'state': 'present', 'files': files, 'bytes': total}


def fixture_root(root, scenario):
    explicit = scenario.get('fixture_root')
    if explicit is not None: return bounded.safe(root, explicit), 'explicit'
    name = scenario['name']
    conventional = bounded.safe(root, 'fixtures/scenarios/' + name)
    return (conventional, 'runtime_convention') if conventional.is_dir() else (bounded.safe(root, 'fixtures/inputs'), 'runtime_fallback')


def public_provenance(workspace, manifest):
    path = workspace / 'workspace.yaml'; expected = manifest.get('workspace_manifest_sha256')
    if not path.is_file() or not expected or sha(path) != expected:
        return {'verified': False, 'reason': 'recorded_workspace_manifest_hash_not_verified'}
    index = document(path); entries = index.get('files')
    if not isinstance(entries, list): raise ValueError('Workspace inventory is unavailable')
    names = [e['path'] for e in entries]
    if len(names) != len(set(names)): raise ValueError('Duplicate workspace inventory path')
    for entry in entries:
        target = bounded.safe(workspace, entry['path'])
        if not target.is_file() or sha(target) != entry['sha256']:
            return {'verified': False, 'reason': 'recorded_public_file_hash_not_verified', 'path': entry['path']}
    actual = tree(workspace / 'fixtures')['files']
    declared = {name.removeprefix('fixtures/') for name in names if name.startswith('fixtures/')}
    if set(actual) != declared:
        return {'verified': False, 'reason': 'public_fixture_inventory_changed'}
    return {'verified': True, 'workspace_manifest_sha256': expected, 'verified_public_files': len(entries)}


def scenario_contexts(root, manifest):
    scenarios = manifest.get('scenarios')
    if not isinstance(scenarios, list) or not scenarios: raise ValueError('Scenario declarations missing')
    names = [s['name'] for s in scenarios]
    if len(names) != len(set(names)): raise ValueError('Duplicate scenario declarations')
    contexts = {}
    for scenario in scenarios:
        params = scenario.get('parameters')
        if not isinstance(params, dict): raise ValueError('Scenario parameter map must be explicit')
        directory, origin = fixture_root(root, scenario)
        contexts[scenario['name']] = {'parameters': params, 'fixture_root': str(directory),
            'fixture_root_policy': origin, 'fixture_tree': tree(directory)}
    return contexts


def context_comparison(left, right):
    lf, rf = left['fixture_tree'], right['fixture_tree']
    shared = set(lf['files']) & set(rf['files'])
    params = (json.dumps(left['parameters'], sort_keys=True, allow_nan=False) ==
              json.dumps(right['parameters'], sort_keys=True, allow_nan=False))
    exact = lf['state'] == rf['state'] == 'present' and lf['files'] == rf['files']
    return {'parameters_exact': params, 'fixture_tree_exact': exact,
        'same_named_file_hashes': sum(lf['files'][name] == rf['files'][name] for name in shared),
        'execution_only_files': sorted(set(lf['files']) - set(rf['files'])),
        'reviewed_only_files': sorted(set(rf['files']) - set(lf['files'])),
        'different_named_file_hashes': sorted(name for name in shared if lf['files'][name] != rf['files'][name]),
        'context_exact': params and exact}


def associate(executions, declared, reviewed, verified_public):
    """Only explicit identical input contexts may support a naming association.

    Names, positions, single CSV overlaps and favorable outputs are never a
    substitute for complete fixture and parameter provenance. This yields
    diagnostic associations, not assertion passes or executable alias rules.
    """
    observed = [s['scenario'] for s in executions]
    if len(observed) != len(set(observed)): raise ValueError('Duplicate recorded execution scenario')
    pairs = []
    for name in observed:
        for target, right in reviewed.items():
            left = declared.get(name)
            comparison = context_comparison(left, right) if left else {'context_exact': False}
            pairs.append({'execution': name, 'reviewed': target, 'runtime_declaration_present': left is not None, **comparison})
    supported = []
    if verified_public:
        direct = [p for p in pairs if p['context_exact'] and p['execution'] == p['reviewed']]
        supported.extend({**p, 'association': 'exact_name_and_context'} for p in direct)
        used_e = {p['execution'] for p in direct}; used_r = {p['reviewed'] for p in direct}
        candidates = [p for p in pairs if p['context_exact'] and p['execution'] not in used_e and p['reviewed'] not in used_r]
        for pair in candidates:
            if (sum(p['execution'] == pair['execution'] for p in candidates) == 1 and
                    sum(p['reviewed'] == pair['reviewed'] for p in candidates) == 1):
                supported.append({**pair, 'association': 'unique_identical_input_context'})
    return {'comparisons': pairs, 'supported_input_associations': supported,
        'reviewed_scenarios_without_supported_association': sorted(set(reviewed) - {p['reviewed'] for p in supported}),
        'unassociated_execution_scenarios': sorted(set(observed) - {p['execution'] for p in supported}),
        'additional_recorded_executions_required_lower_bound': max(0, len(reviewed) - len(observed)),
        'note': 'Input-context association alone neither proves task correctness nor supplies execution snapshots.'}


def retained_outputs(submission, assertions):
    """Loose files are inventory, never a provenance-bound execution snapshot."""
    paths = sorted({a['path'] for scenario in assertions['scenarios'] for a in scenario['assertions']})
    files = []
    for relative in paths:
        path = bounded.safe(submission, relative)
        files.append({'path': relative, 'state': 'present' if path.is_file() else 'not_retained_at_expected_path',
                      'sha256': sha(path) if path.is_file() else None})
    return {'expected_output_inventory': files, 'loose_expected_files_present': sum(r['state'] == 'present' for r in files),
        'provenance_bound_snapshot_available': False, 'offline_rescoring_authorized': False,
        'scope': 'Original score reports do not retain the scorer temporary workspace snapshots. Loose submission files are not automatically associated with a recorded execution, and no program is run to reconstruct them.'}


def inspect(cell, row, posthoc, benchmark, expected_workspace):
    score_path = Path(cell['score_path']); score = document(score_path)
    manifest_path = Path(row['manifest_path']); manifest = document(manifest_path)
    submission = Path(cell['saved_ir_path']).parent.resolve(); workspace = Path(score['workspace']).resolve()
    if Path(score['submission']).resolve() != submission or workspace != Path(expected_workspace).resolve():
        raise ValueError('Original score/workspace/submission identity differs')
    if score_path.parent != manifest_path.parent or row['semantic_source'] != 'posthoc_scorer_1.2.1' or row['semantic_success'] != '0':
        raise ValueError('Publication evidence identity/source differs')
    report = posthoc['g6_assert']; executions = report.get('scenarios', [])
    if posthoc['semantic_success'] is not False: raise ValueError('Publication result differs')
    provenance = public_provenance(workspace, manifest)
    runtime = document(submission / 'runtime/manifest.yaml')
    instance = Path(benchmark) / 'instances' / cell['case']
    reviewed_runtime = document(instance / 'runtime/manifest.yaml')
    assertions = document(instance / 'gold/assertions.yaml')
    names = [s['scenario'] for s in assertions['scenarios']]
    if not names or len(names) != len(set(names)) or set(names) != {s['name'] for s in reviewed_runtime['scenarios']}:
        raise ValueError('Reviewed runtime/assertion scenario rosters differ')
    contexts = scenario_contexts(workspace, runtime); reviewed = scenario_contexts(instance, reviewed_runtime)
    comparison = associate(executions, contexts, reviewed, provenance['verified'])
    output = retained_outputs(submission, assertions)
    return {'id': cell['id'], 'model': cell['model'], 'method': cell['method'], 'case': cell['case'], 'sample_index': cell['sample_index'],
        'state': 'inspected', 'published_semantic_success': False, 'source_score': str(score_path), 'source_manifest': str(manifest_path),
        'original_ir': cell['saved_ir_path'], 'public_workspace': str(workspace), 'public_provenance': provenance,
        'recorded_execution_scenarios': [{'scenario': s['scenario'], 'execution_status': s.get('execution_status'),
             'scoring_error': s.get('scoring_error'), 'matched_assertion_count': len(s.get('assertions', []))} for s in executions],
        'execution_contexts': contexts, 'reviewed_contexts': reviewed, **comparison, 'retained_outputs': output,
        'published_unmatched_execution_scenarios': report.get('unmatched_execution_scenarios', []),
        'published_unmatched_assertion_scenarios': report.get('unmatched_assertion_scenarios', []),
        'reviewed_assertion_counts': {s['scenario']: len(s['assertions']) for s in assertions['scenarios']},
        'raw_manifest_full_pass_flag': manifest.get('evaluation', {}).get('score_summary', {}).get('full_pass_g0_g6'),
        'new_semantic_score': None, 'rescored': False,
        'interpretation': 'Recorded scenario coverage and input/output provenance only. Missing evidence is not a demonstrated business error. Original results are unchanged.'}
