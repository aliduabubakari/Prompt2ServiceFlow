"""Authored scenario-handoff controls and explicitly labeled snapshot mutants."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil

import csv_ir_adapter_controls as authored
import scenario_suite as suite

RAW = b'item,amount\nfirst,10\nsecond,20\n'
CHANGED = b'item,amount\nfirst,10\nsecond,changed\nsecond,changed\n'
MUTANTS = ['missing_scenario', 'duplicate_scenario', 'reuse_positive_snapshot', 'ignored_parameters',
           'constant_success_empty_target', 'wrong_business_value', 'unsealed_output_tamper', 'missing_snapshot_manifest']


def make_control(root, service, schemas):
    root = Path(root); root.mkdir(parents=True, exist_ok=False)
    ir, intervention = authored.authored(RAW, service, root / 'original_inputs')
    ir = authored.renamed(ir)
    plan = suite.adapter.compile_projection(ir, intervention, schemas)
    row = {'source': {'id': 'authored/' + service}, 'artifact_sha256': suite.adapter.digest(ir), 'plan': plan,
           'fixture_sources': {ref: str(root / 'original_inputs' / entry['path']) for ref, entry in intervention['fixtures'].items()},
           'target': {'schema': 'p2sf_adapter', 'table': 'records_generic', 'logical_name': 'p2sf_adapter.records_generic',
                      'loader_service': service, 'write_mode': 'replace'}}
    pool = root / 'scenario_pool'; pool.mkdir()
    (pool / 'batch_17.csv').write_bytes(RAW); (pool / 'batch_changed.csv').write_bytes(CHANGED)
    scenarios = [{'name': name, 'parameters': {'selected-file': filename}} for name, filename in
        [('present_case', 'batch_17.csv'), ('absent_case', 'batch_absent.csv'), ('changed_case', 'batch_changed.csv')]]
    specs = [suite.spec(row, s, pool, 'selected-file') for s in scenarios]
    paths = {}
    for node in plan['nodes'].values():
        paths.update({port: 'artifacts/' + aid + '.json' for port, aid in node['outputs'].items()})
    predicates = {}
    for value in specs:
        if value['selected_sha256'] == 'MISSING':
            definitions = [{'assertion_id': 'unavailable', 'type': 'json_path_equals', 'path': paths['availability_decision'], 'json_path': 'available', 'expected': False},
                {'assertion_id': 'validator_skipped', 'type': 'file_absent', 'path': paths['validation_status']},
                {'assertion_id': 'loader_skipped', 'type': 'file_absent', 'path': paths['load_status']}]
        else:
            count = len(suite.oracle.expected_csv(Path(value['selected_path']).read_bytes())[1])
            definitions = [{'assertion_id': 'available', 'type': 'json_path_equals', 'path': paths['availability_decision'], 'json_path': 'available', 'expected': True},
                {'assertion_id': 'validated', 'type': 'json_path_equals', 'path': paths['validation_status'], 'json_path': 'success', 'expected': True},
                {'assertion_id': 'count', 'type': 'json_path_equals', 'path': paths['load_status'], 'json_path': 'rows_loaded', 'expected': count}]
        predicates[value['scenario_id']] = definitions
    suite.write(root / 'authored_ir.json', ir); suite.write(root / 'authored_specs.json', specs); suite.write(root / 'authored_predicates.json', predicates)
    return row, specs, predicates


def mutate_controls(root, specs, results, directories, definitions):
    root = Path(root); root.mkdir(parents=True, exist_ok=False)
    positive, negative = specs[0], specs[1]; positive_dir = Path(directories[0])
    outcomes = {}
    outcomes['missing_scenario'] = not suite.aggregate(specs, results[:-1])['suite_pass']
    outcomes['duplicate_scenario'] = not suite.aggregate(specs, results + [results[0]])['suite_pass']
    outcomes['reuse_positive_snapshot'] = not suite.score(positive_dir, negative, definitions[negative['scenario_id']])['pass']
    for name in MUTANTS[3:]:
        directory = root / name; shutil.copytree(positive_dir, directory)
        snapshot = directory / 'output_snapshot'; expected = positive
        if name == 'ignored_parameters':
            # A deliberately faulty runner claims the negative ID/parameters,
            # but its genuine copied input/data observations are positive.
            expected = negative
            p = suite.read(snapshot / 'execution_provenance.json')
            for key in ('scenario_id', 'parameters', 'spec_sha256'): p[key] = negative[key]
            suite.write(snapshot / 'execution_provenance.json', p)
            receipt = suite.read(snapshot / 'input_receipt.json')
            receipt.update(parameters=negative['parameters'], spec_sha256=negative['spec_sha256'], selected_sha256='MISSING')
            suite.write(snapshot / 'input_receipt.json', receipt)
            suite.seal_snapshot(directory)
        elif name == 'constant_success_empty_target':
            # Reuse a real observed empty before-state as a counterexample to
            # positive success/count flags. This is a mutant, not an execution.
            suite.write(snapshot / 'database/after.json', suite.read(snapshot / 'database/before.json'))
            suite.seal_snapshot(directory)
        elif name == 'wrong_business_value':
            state = suite.read(snapshot / 'database/after.json'); state['rows'][0][-1] += '__CORRUPT__'
            suite.write(snapshot / 'database/after.json', state); suite.seal_snapshot(directory)
        elif name == 'unsealed_output_tamper':
            path = next((snapshot / 'artifacts').glob('*availability_decision.json')); suite.write(path, {'available': False})
        elif name == 'missing_snapshot_manifest': (directory / 'snapshot_manifest.json').unlink()
        checked = suite.score(directory, expected, definitions[expected['scenario_id']])
        suite.write(directory / 'mutant_result.json', {'mutant': name, 'fabricated_or_mutated_evidence': True, 'checked': checked})
        outcomes[name] = not checked['pass']
        if name in ('constant_success_empty_target', 'wrong_business_value'):
            outcomes[name] = outcomes[name] and all(a['pass'] for a in checked['assertions']) and not all(checked['business_checks'].values())
    suite.write(root / 'results.json', outcomes)
    return outcomes


def run(root, service, schemas, image):
    root = Path(root); row, specs, predicates = make_control(root, service, schemas)
    results, directories = [], []
    for value in specs:
        directory = root / 'executions' / value['scenario_id']; suite.execute(row, value, directory, image)
        checked = suite.score(directory, value, predicates[value['scenario_id']]); suite.write(directory / 'score.json', checked)
        results.append(checked); directories.append(str(directory))
    summary = suite.aggregate(specs, results)
    mutants = mutate_controls(root / 'mutants', specs, results, directories, predicates)
    summary.update(control_service=service, mutants=mutants, control_gate_pass=summary['suite_pass'] and all(mutants.values()))
    suite.write(root / 'result.json', summary)
    return summary
