"""Avoid paid redispatch, preserve failed pilot cells and validate provenance."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import continue_v2_fusion_qwen_seeds as continuation


def fixture_prepared(tmp_path):
    model = 'test-model'
    cells = [[model, m, seed] for seed in [101, 202, 303] for m in ['m3', 'm4', 'm5']]
    source = {'result_files': {}}
    for cell in cells[:3]:
        directory = tmp_path / 'pilot' / continuation.key(cell).replace('/', '_'); directory.mkdir(parents=True)
        row = result(cell, business=cell[1] != 'm5')
        continuation.frozen.controls.write_json(directory / 'result.json', row)
        source['result_files'][continuation.key(cell)] = continuation.frozen.generation.output_checkpoint(directory)
    spec = {'cells': cells, 'retained_cells': cells[:3], 'new_cells': cells[3:],
            'model': model, 'images': {'agent': 'same-agent', 'proxy': 'same-proxy'},
            'source_directory': str(tmp_path / 'pilot')}
    prepared = {'continuation': spec, 'source_run': source, 'design': {'case': 'development/task'},
                'hashes': {}, 'freeze': {'freeze_id': 'unchanged-v2.3'},
                'continuation_manifest': {'status': 'frozen', 'specification': spec}}
    output = tmp_path / 'continuation'; output.mkdir()
    run = {'freeze': prepared['freeze'], 'cells': cells, 'images': spec['images'],
           'input_fingerprint': continuation.frozen.controls.fingerprint({}),
           'continuation_manifest': prepared['continuation_manifest'],
           'result_files': copy.deepcopy(source['result_files'])}
    return prepared, output, run


def result(cell, *, business=True):
    return {'model': cell[0], 'method': cell[1], 'seed': cell[2], 'case': 'development/task',
        'validity': 'valid', 'usage': {'total_tokens': 10},
        'evaluation': {'state': 'evaluated' if business else 'blocked_public_gates',
                       'business_pass': business if business else None,
                       'public_overall': 'pass' if business else 'fail'}}


def test_dispatches_only_six_new_cells_and_never_retries_retained_nonpass(tmp_path, monkeypatch):
    prepared, output, run = fixture_prepared(tmp_path)
    retained = copy.deepcopy(run['result_files'])
    calls = []
    def dispatch(p, model, method, seed, directory, skip_images):
        assert p is prepared and skip_images is True
        cell = [model, method, seed]; calls.append(cell)
        directory.mkdir(parents=True)
        row = result(cell)
        continuation.frozen.controls.write_json(directory / 'result.json', row)
        return row
    monkeypatch.setattr(continuation.frozen.runner, 'execute_cell', dispatch)
    continuation.execute_pending(prepared, output, run)
    assert calls == prepared['continuation']['new_cells'] and len(calls) == 6
    assert all(run['result_files'][k] == v for k, v in retained.items())
    assert continuation.frozen.replay.read_json(Path(run['result_files']['test-model/m5/101']['path']))['evaluation']['business_pass'] is None
    continuation.execute_pending(prepared, output, run)
    assert len(calls) == 6
    continuation.verify_run(run, prepared)


def test_interrupted_attempt_is_recorded_without_another_paid_call(tmp_path, monkeypatch):
    prepared, output, run = fixture_prepared(tmp_path)
    cell = prepared['continuation']['new_cells'][0]
    prepared['continuation']['new_cells'] = [cell]
    index = prepared['continuation']['cells'].index(cell)
    target = output / 'cells' / f'{index:03d}_{cell[0]}_{cell[1]}_{cell[2]}'
    target.mkdir(parents=True)
    (target / 'request_started.json').write_text('{}')
    def forbidden(*args): pytest.fail('Interrupted request must not be redispatched')
    monkeypatch.setattr(continuation.frozen.runner, 'execute_cell', forbidden)
    continuation.execute_pending(prepared, output, run)
    row = continuation.frozen.replay.read_json(target / 'result.json')
    assert row['validity'] == 'invalid_interrupted_attempt'
    assert row['evaluation']['evaluated'] is False
    assert (target / 'request_started.json').exists()


def test_saved_uncheckpointed_result_is_adopted_and_wrong_identity_rejected(tmp_path, monkeypatch):
    prepared, output, run = fixture_prepared(tmp_path)
    cell = prepared['continuation']['new_cells'][0]
    prepared['continuation']['new_cells'] = [cell]
    index = prepared['continuation']['cells'].index(cell)
    target = output / 'cells' / f'{index:03d}_{cell[0]}_{cell[1]}_{cell[2]}'
    target.mkdir(parents=True)
    row = result(cell); row['seed'] = 999
    continuation.frozen.controls.write_json(target / 'result.json', row)
    def forbidden(*args): pytest.fail('Existing result must not be redispatched')
    monkeypatch.setattr(continuation.frozen.runner, 'execute_cell', forbidden)
    with pytest.raises(ValueError, match='identity differs'):
        continuation.execute_pending(prepared, output, run)
    row['seed'] = cell[2]
    continuation.frozen.controls.write_json(target / 'result.json', row)
    continuation.execute_pending(prepared, output, run)
    assert continuation.key(cell) in run['result_files']


def test_resume_rejects_changed_images_or_retained_checkpoint(tmp_path):
    prepared, _, run = fixture_prepared(tmp_path)
    changed = copy.deepcopy(run); changed['images']['agent'] = 'different'
    with pytest.raises(ValueError, match='cannot resume'): continuation.verify_run(changed, prepared)
    changed = copy.deepcopy(run); changed['result_files']['test-model/m5/101']['sha256'] = 'changed'
    with pytest.raises(ValueError, match='Retained seed-101 checkpoint'): continuation.verify_run(changed, prepared)


def test_summary_preserves_failure_and_separates_retained_usage(tmp_path, monkeypatch):
    prepared, output, run = fixture_prepared(tmp_path)
    def original_report(destination, record):
        assert record is run
        (destination / 'summary.md').write_text('# Original per-cell report\n')
    monkeypatch.setattr(continuation.frozen.runner, 'report', original_report)
    continuation.write_report(output, run)
    text = (output / 'summary.md').read_text()
    assert '| m5 | 3 | 1 | 0 | 0 | 0 |' in text
    assert 'Retained tokens: 30.' in text and 'New-attempt tokens: 0.' in text
    assert 'not independent pipelines or held-out validation' in text


def test_original_freeze_inventory_exclusion_is_exact_and_restored(monkeypatch):
    other = ROOT / 'audit/v2/fusion_public_tools_v2_3.py'
    def original_inventory(): return [continuation.SCRIPT, other]
    monkeypatch.setattr(continuation.frozen.runner, 'implementation_files', original_inventory)
    def checked_prepare():
        assert continuation.frozen.runner.implementation_files() == [other]
        return {'checked': True}
    monkeypatch.setattr(continuation.frozen, 'prepare', checked_prepare)
    assert continuation.prepare_original() == {'checked': True}
    assert continuation.frozen.runner.implementation_files is original_inventory


def test_second_default_run_is_blocked_before_dispatch(tmp_path, monkeypatch):
    prepared, _, _ = fixture_prepared(tmp_path)
    existing = tmp_path / 'audit/outputs' / (continuation.PREFIX + 'existing')
    existing.mkdir(parents=True); (existing / 'run.json').write_text('{}')
    monkeypatch.setattr(continuation, 'ROOT', tmp_path)
    def forbidden(*args): pytest.fail('Duplicate default command must not dispatch')
    monkeypatch.setattr(continuation.frozen.runner, 'execute_cell', forbidden)
    with pytest.raises(ValueError, match='resume it with --resume'):
        continuation.run_locked(SimpleNamespace(resume=None), prepared)


def test_resume_checks_retained_file_bytes(tmp_path):
    prepared, _, run = fixture_prepared(tmp_path)
    path = Path(run['result_files']['test-model/m5/101']['path'])
    path.write_text(path.read_text() + '\n')
    with pytest.raises(ValueError): continuation.verify_run(run, prepared)
