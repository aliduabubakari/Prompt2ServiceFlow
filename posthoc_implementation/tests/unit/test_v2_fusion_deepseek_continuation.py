"""Second-model dispatch, retained failures, provenance and offline dry run."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import continue_v2_fusion_deepseek as continuation


def result(cell, *, valid=True, passed=True):
    return {'model': cell[0], 'method': cell[1], 'seed': cell[2], 'case': 'development/task',
        'validity': 'valid' if valid else 'invalid_infrastructure_or_provider',
        'usage': {'total_tokens': 12},
        'evaluation': {'state': 'evaluated' if passed and valid else 'blocked_public_gates',
                       'public_overall': 'pass' if passed and valid else 'fail',
                       'business_pass': True if passed and valid else None}}


def fixture_prepared(tmp_path):
    qwen, deepseek = 'test-qwen', 'test-deepseek'
    retained = [[qwen, m, seed] for seed in [101, 202, 303] for m in ['m3', 'm4', 'm5']]
    new = [[deepseek, m, seed] for seed in [101, 202, 303] for m in ['m3', 'm4', 'm5']]
    source = {'result_files': {}}
    for cell in retained:
        directory = tmp_path / 'qwen' / continuation.key(cell).replace('/', '_'); directory.mkdir(parents=True)
        # Include every original kind of non-pass; none is filtered or retried.
        passed = cell[1] != 'm5' and cell[1:] not in [['m3', 202], ['m4', 303]]
        continuation.frozen.controls.write_json(directory / 'result.json', result(cell, passed=passed))
        source['result_files'][continuation.key(cell)] = continuation.frozen.generation.output_checkpoint(directory)
    spec = {'cells': retained + new, 'retained_cells': retained, 'new_cells': new,
            'model': deepseek, 'case': 'development/task', 'method_freeze_id': 'same-v2.3',
            'images': {'agent': 'same-agent', 'proxy': 'same-proxy'}, 'source_directory': str(tmp_path / 'qwen')}
    prepared = {'continuation': spec, 'source_run': source, 'design': {'case': 'development/task'},
                'hashes': {}, 'freeze': {'freeze_id': 'same-v2.3'},
                'continuation_manifest': {'status': 'frozen', 'specification': spec}}
    output = tmp_path / 'deepseek'; output.mkdir()
    run = {'freeze': prepared['freeze'], 'cells': spec['cells'], 'images': spec['images'],
           'input_fingerprint': continuation.frozen.controls.fingerprint({}),
           'continuation_manifest': prepared['continuation_manifest'],
           'result_files': copy.deepcopy(source['result_files'])}
    return prepared, output, run


def test_only_nine_deepseek_cells_are_dispatched_and_qwen_failures_are_retained(tmp_path, monkeypatch):
    prepared, output, run = fixture_prepared(tmp_path)
    source = copy.deepcopy(run['result_files']); calls = []
    def dispatch(p, model, method, seed, directory, skip_images):
        assert p is prepared and skip_images is True and model == 'test-deepseek'
        cell = [model, method, seed]; calls.append(cell); directory.mkdir(parents=True)
        row = result(cell, passed=method != 'm5')
        continuation.frozen.controls.write_json(directory / 'result.json', row)
        return row
    monkeypatch.setattr(continuation.frozen.runner, 'execute_cell', dispatch)
    continuation.execute_pending(prepared, output, run)
    continuation.execute_pending(prepared, output, run)
    assert calls == prepared['continuation']['new_cells'] and len(calls) == 9
    assert len(run['result_files']) == 18
    assert all(run['result_files'][k] == v for k, v in source.items())
    for seed in [101, 202, 303]:
        r = continuation.frozen.replay.read_json(Path(run['result_files'][f'test-qwen/m5/{seed}']['path']))
        assert r['evaluation']['business_pass'] is None
    continuation.verify_run(run, prepared)


def test_interrupted_deepseek_call_is_not_repeated(tmp_path, monkeypatch):
    prepared, output, run = fixture_prepared(tmp_path)
    cell = prepared['continuation']['new_cells'][0]; prepared['continuation']['new_cells'] = [cell]
    index = prepared['continuation']['cells'].index(cell)
    target = output / 'cells' / f'{index:03d}_{cell[0]}_{cell[1]}_{cell[2]}'
    target.mkdir(parents=True); (target / 'request_started.json').write_text('{}')
    def forbidden(*args): pytest.fail('Never repeat an interrupted paid call')
    monkeypatch.setattr(continuation.frozen.runner, 'execute_cell', forbidden)
    continuation.execute_pending(prepared, output, run)
    r = continuation.frozen.replay.read_json(target / 'result.json')
    assert r['validity'] == 'invalid_interrupted_attempt'


def test_resume_rejects_changed_image_or_any_retained_qwen_checkpoint(tmp_path):
    prepared, _, run = fixture_prepared(tmp_path)
    changed = copy.deepcopy(run); changed['images']['agent'] = 'different'
    with pytest.raises(ValueError, match='cannot resume'): continuation.verify_run(changed, prepared)
    changed = copy.deepcopy(run); changed['result_files']['test-qwen/m4/303']['sha256'] = 'different'
    with pytest.raises(ValueError, match='checkpoint differs'): continuation.verify_run(changed, prepared)
    path = Path(run['result_files']['test-qwen/m5/303']['path']); path.write_text(path.read_text() + '\n')
    with pytest.raises(ValueError): continuation.verify_run(run, prepared)


def test_model_method_summary_counts_invalids_and_separates_new_tokens(tmp_path, monkeypatch):
    prepared, output, run = fixture_prepared(tmp_path)
    for cell in prepared['continuation']['new_cells']:
        directory = output / continuation.key(cell).replace('/', '_'); directory.mkdir()
        row = result(cell, valid=cell[1:] != ['m5', 303], passed=cell[1] != 'm5')
        continuation.frozen.controls.write_json(directory / 'result.json', row)
        run['result_files'][continuation.key(cell)] = continuation.frozen.generation.output_checkpoint(directory)
    def original_report(destination, record): (destination / 'summary.md').write_text('# Per-cell rows\n')
    monkeypatch.setattr(continuation.frozen.runner, 'report', original_report)
    continuation.write_report(output, run)
    text = (output / 'summary.md').read_text()
    assert '| test-qwen | m3 | 3 | 3 | 0 | 2 | 2 |' in text
    assert '| test-qwen | m5 | 3 | 3 | 0 | 0 | 0 |' in text
    assert '| test-deepseek | m5 | 3 | 3 | 1 | 0 | 0 |' in text
    assert 'Retained Qwen tokens: 108.' in text and 'New DeepSeek attempt tokens: 108.' in text
    assert 'not nine tasks' in text


def test_duplicate_default_run_is_blocked_before_dispatch(tmp_path, monkeypatch):
    prepared, _, _ = fixture_prepared(tmp_path)
    existing = tmp_path / 'audit/outputs' / (continuation.PREFIX + 'existing'); existing.mkdir(parents=True)
    (existing / 'run.json').write_text('{}')
    monkeypatch.setattr(continuation.module, 'ROOT', tmp_path)
    def forbidden(*args): pytest.fail('Duplicate default run must not dispatch')
    monkeypatch.setattr(continuation.frozen.runner, 'execute_cell', forbidden)
    with pytest.raises(ValueError, match='resume it with --resume'):
        continuation.module.run_locked(SimpleNamespace(resume=None), prepared)


@pytest.mark.parametrize('raises', [False, True])
def test_nested_original_inventory_exclusions_are_exact_and_restored(monkeypatch, raises):
    public_tool = ROOT / 'audit/v2/fusion_public_tools_v2_3.py'
    def original(): return [continuation.SCRIPT, continuation.qwen.SCRIPT, public_tool]
    monkeypatch.setattr(continuation.frozen.runner, 'implementation_files', original)
    def original_prepare():
        assert continuation.frozen.runner.implementation_files() == [public_tool]
        if raises: raise RuntimeError('test interruption')
        return {'verified': True}
    monkeypatch.setattr(continuation.frozen, 'prepare', original_prepare)
    monkeypatch.setattr(continuation.qwen, 'prepare', continuation.qwen.prepare_original)
    if raises:
        with pytest.raises(RuntimeError): continuation.prepare_qwen()
    else: assert continuation.prepare_qwen() == {'verified': True}
    assert continuation.frozen.runner.implementation_files is original


def test_dry_run_does_not_dispatch_or_touch_docker(tmp_path, monkeypatch, capsys):
    prepared, _, _ = fixture_prepared(tmp_path)
    monkeypatch.setattr(continuation, 'prepare', lambda: prepared)
    def forbidden(*args): pytest.fail('Dry run cannot dispatch inference')
    monkeypatch.setattr(continuation.module, 'run_locked', forbidden)
    monkeypatch.setattr(continuation.frozen.bridge, 'agent_module', forbidden)
    assert continuation.main(['--dry-run']) == 0
    assert 'Retained Qwen: 9; new DeepSeek: 9; total: 18 cells' in capsys.readouterr().out
