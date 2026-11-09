"""Reference/public-input coverage only; never infer semantic equivalence."""
from __future__ import annotations

import ast
from collections import Counter
import csv
import io
import json
from pathlib import Path
import re


def contained(root, relative):
    root = Path(root).resolve()
    path = Path(relative)
    result = (root / path).resolve()
    if path.is_absolute() or '..' in path.parts or not result.is_relative_to(root):
        raise ValueError('Public path escapes its declared root: ' + str(relative))
    return result


def registry_keys(path, assignment):
    """Read dictionary keys, not executable function values, from trusted code."""
    tree = ast.parse(Path(path).read_text())
    nodes = [n.value for n in tree.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == assignment for t in n.targets)]
    if len(nodes) != 1 or not isinstance(nodes[0], ast.Dict):
        raise ValueError('Registry declaration changed: ' + str(path))
    keys = [ast.literal_eval(k) for k in nodes[0].keys]
    if any(not isinstance(k, str) for k in keys) or len(keys) != len(set(keys)):
        raise ValueError('Invalid or duplicate registry keys')
    return keys


def constant_strings(path, names):
    tree = ast.parse(Path(path).read_text()); values = {}
    for n in tree.body:
        if isinstance(n, ast.Assign):
            for target in n.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    values[target.id] = ast.literal_eval(n.value)
    if set(values) != set(names) or any(not isinstance(v, str) for v in values.values()):
        raise ValueError('Public service constants changed')
    return list(values.values())


def public_inventory(workspace, load, sha):
    workspace = Path(workspace)
    manifest = load(workspace / 'workspace.yaml')
    for item in manifest['files']:
        path = contained(workspace, item['path'])
        if not path.is_file() or sha(path) != item['sha256']:
            raise ValueError('Public builder inventory differs: ' + item['path'])
    task = (workspace / 'task.md').read_text()
    # Signals are review aids, never proof that a requirement is implemented.
    terms = ['freshness', 'hourly', 'daily', 'forecast', 'align', 'lookup', 'delete', 'database', 'stream']
    return {'task': task, 'task_sha256': sha(workspace / 'task.md'),
            'verified_public_files': len(manifest['files']),
            'review_signals': [t for t in terms if re.search(r'\b' + t + r'\w*\b', task, re.I)]}


def input_inventory(workspace, max_bytes):
    """Validate only named public sources; never invent an absent source role."""
    workspace = Path(workspace)
    nominal = workspace / 'fixtures/scenarios/nominal'
    manifest = nominal / 'fixture.json'
    report = {'manifest_present': manifest.is_file(), 'inputs': [], 'findings': [],
              'manifest': None, 'unmapped_public_input_files': []}
    source_root = workspace / 'fixtures/inputs'
    if source_root.is_dir():
        report['unmapped_public_input_files'] = sorted(p.relative_to(workspace).as_posix()
            for p in source_root.rglob('*') if p.is_file())
    if not manifest.is_file():
        report['state'] = 'public_files_without_manifest_mapping' if report['unmapped_public_input_files'] else 'no_public_input_files'
        return report
    if manifest.stat().st_size > max_bytes: raise ValueError('Public manifest exceeds inspection limit')
    document = json.loads(manifest.read_text())
    if not isinstance(document, dict) or not isinstance(document.get('inputs'), dict):
        report['state'] = 'manifest_roles_unmapped'
        report['findings'].append('manifest_inputs_not_a_mapping'); return report
    report['manifest'] = document
    for role, relative in sorted(document['inputs'].items()):
        item = {'role': role, 'path': relative, 'present': False, 'shape': 'uninspected', 'fields': []}
        if not isinstance(relative, str) or '://' in relative:
            item['shape'] = 'nonlocal_or_unresolved_source'; report['findings'].append('nonlocal_or_unresolved_source:' + role)
        else:
            path = contained(nominal, relative)
            item['present'] = path.is_file()
            if not item['present']: report['findings'].append('missing_named_source:' + role)
            elif path.stat().st_size > max_bytes:
                item['shape'] = 'inspection_limit'; report['findings'].append('source_inspection_limit:' + role)
            else:
                try:
                    if path.suffix.lower() == '.csv':
                        reader = csv.DictReader(io.StringIO(path.read_text()))
                        item.update(shape='csv', fields=reader.fieldnames or [])
                        # Headers are a structural check, not successful processing.
                        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                            report['findings'].append('invalid_csv_header:' + role)
                    elif path.suffix.lower() in ('.json', '.jsonl', '.ndjson'):
                        values = ([json.loads(line) for line in path.read_text().splitlines() if line.strip()]
                                  if path.suffix.lower() != '.json' else json.loads(path.read_text()))
                        if isinstance(values, list):
                            objects = [v for v in values if isinstance(v, dict)]
                            common = set.intersection(*(set(v) for v in objects)) if objects else set()
                            item.update(shape='records' if len(objects) == len(values) else 'mixed_array',
                                        fields=sorted(common), row_count=len(values))
                        elif isinstance(values, dict): item.update(shape='object', fields=sorted(values))
                        else: item['shape'] = 'scalar'
                    else: item['shape'] = 'other_public_file'
                except (ValueError, UnicodeError, csv.Error) as exc:
                    item['shape'] = 'parse_error'; report['findings'].append('source_parse_error:' + role + ':' + type(exc).__name__)
        report['inputs'].append(item)
    report['state'] = 'named_sources_present' if not report['findings'] else 'named_source_review_required'
    return report


def profile_checks(inputs, review, load_profile):
    """Only explicitly registered task/profile mappings can be checked."""
    if review is None: return {'state': 'no_task_profile_registered', 'findings': []}
    profile = load_profile(review['profile_file'])
    sources = {row['role']: row for row in inputs['inputs']}
    findings = []
    if review['backend'] == 'window':
        roles = profile['input_keys']; fields = profile['fields']
        expected = {roles['records']: ('records', [fields[k] for k in ('entity', 'group', 'time', 'energy', 'demand', 'quality')]),
                    roles['registry']: ('csv', [fields[k] for k in ('group', 'capacity')])}
        required_config = ['batch_window_start', 'batch_window_end', 'window_size_minutes', 'demand_threshold_pct', 'power_factor_min']
    elif review['backend'] == 'relational':
        roles = profile['inputs']; fields = profile['fields']
        expected = {roles['primary']: ('records', [fields[k] for k in ('record_id', 'join_key', 'priority', 'category')]),
            roles['secondary']: ('csv', [fields[k] for k in ('join_key', 'tier', 'churn')] + fields['numeric_lookup_fields']),
            roles['reference']: ('object', ['priority_weights', 'tier_multipliers', 'escalation_threshold', 'churn_high_priority_threshold', 'categories_requiring_immediate'])}
        required_config = []
    else: raise ValueError('No profile inspection for this backend')
    for role, (shape, names) in expected.items():
        source = sources.get(role)
        if source is None: findings.append('missing_explicit_profile_role:' + role); continue
        if source['shape'] != shape: findings.append('profile_source_shape:' + role)
        missing = sorted(set(names) - set(source['fields']))
        if missing: findings.append('profile_source_fields:' + role + ':' + ','.join(missing))
    config = inputs['manifest'] or {}
    findings += ['missing_public_config:' + name for name in required_config if name not in config]
    return {'state': 'structural_profile_match' if not findings else 'profile_input_review_required', 'findings': findings,
            'note': 'Field/shape presence only; no numerical execution or task-equivalence proof'}


def classify(case, bindings, backends, inputs, review, profile):
    required = Counter((b['service_id'], b['service_version']) for b in bindings)
    if not required: raise ValueError('Empty reference service roster')
    registry = {key for b in backends.values() for key in b['services']}
    matched = sorted(k for k in required if k in registry)
    missing = sorted(k for k in required if k not in registry)
    exact = []
    for name, backend in backends.items():
        if backend['exact_roster']:
            fits = required == Counter(backend['services'])
        else: fits = set(required).issubset(backend['services'])
        if fits: exact.append(name)
    development = bool(review and review.get('existing_development_case'))
    issues = list(inputs['findings']) + list(profile['findings'])
    # The relational implementation requires three distinct public source roles.
    if 'relational' in exact and len(inputs['inputs']) < 3:
        issues.append('three_source_runtime_requires_three_explicit_public_source_roles')
    if missing: state = 'unsupported_operations'
    elif not exact: state = 'cross_backend_or_roster_composition_unverified'
    elif not any(backends[b]['method_route'] for b in exact): state = 'mechanism_only_no_ir_method_route'
    elif issues: state = 'public_input_contract_review_required'
    elif development: state = 'clarified_development_scope_only'
    else: state = 'public_semantics_and_profile_review_required'
    # Static inspection cannot authorize a new model experiment. Even a prior
    # development success does not establish coverage of the original task.
    return {'case': case, 'stratum': case.split('/')[0], 'state': state,
        'reference_service_count': sum(required.values()), 'unique_reference_services': len(required),
        'registered_services': [s + '@' + v for s, v in matched],
        'missing_services': [s + '@' + v for s, v in missing], 'complete_backend_rosters': exact,
        'existing_development_case': development, 'original_task_semantics': 'clarified_or_partial' if development else 'not_certified',
        'semantic_review': review, 'profile_check': profile, 'input_findings': sorted(set(issues)),
        'new_generation_ready': False, 'reference_controls_executed': False,
        'semantic_success': None}


def summarize(rows):
    backlog = {}
    for row in rows:
        for service in row.get('missing_services', []): backlog.setdefault(service, []).append(row['case'])
    queue = sorted((r for r in rows if not r.get('existing_development_case') and r['state'] != 'inspection_error'),
        key=lambda r: (len(r['missing_services']), len(r['input_findings']), r['unique_reference_services'], r['case']))
    return {'pipelines': len(rows), 'strata': dict(Counter(r['stratum'] for r in rows)),
        'states': dict(Counter(r['state'] for r in rows)),
        'complete_backend_roster_cases': [r['case'] for r in rows if r.get('complete_backend_rosters')],
        'new_generation_ready': 0, 'workflow_executions': 0, 'llm_calls': 0,
        'review_queue': [{'rank': i + 1, 'case': r['case'], 'state': r['state'], 'missing_services': r['missing_services'],
                          'input_findings': r['input_findings']} for i, r in enumerate(queue)],
        'implementation_backlog': [{'service': k, 'cases': sorted(v), 'case_count': len(v)}
                                   for k, v in sorted(backlog.items(), key=lambda p: (-len(p[1]), p[0]))],
        'scope': 'Static reference/public planning; no original-task semantic certification or model-score-based selection'}
