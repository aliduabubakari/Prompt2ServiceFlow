"""Reproduce the publisher defect and test the production public-executor path."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_fusion_v2_2 as runner

spec = importlib.util.spec_from_file_location('relational_v21_examples', ROOT / 'tests/unit/test_v2_fusion.py')
examples = importlib.util.module_from_spec(spec); spec.loader.exec_module(examples)


def run_scripts(public, value, profile, inputs, root, scripts):
    scripts.mkdir()
    errors = []
    for intent in public.checked_plan(value, profile)['order']:
        script = scripts / (intent + '.py'); script.write_text(public.task_script(value, profile, intent))
        result = subprocess.run([sys.executable, '-I', str(script), '--workspace', str(root), '--fixtures', str(inputs)], capture_output=True, text=True)
        if result.returncode: errors.append(result.stderr); break
    return examples.snapshot(root, 'nominal', errors)


def test_frozen_jobs_reproduce_old_failure_and_corrected_jobs_pass_same_alias(tmp_path):
    profile, value = examples.profile(), examples.ir()
    inputs = tmp_path / 'inputs'; examples.fixtures(inputs, profile)
    actual = tmp_path / 'actual'; actual.mkdir()
    alias = tmp_path / 'alias'; alias.symlink_to(actual, target_is_directory=True)
    old = run_scripts(runner.frozen_v2_1.public, value, profile, inputs, alias, tmp_path / 'old_scripts')
    trace = json.loads(old['_snapshot']['logs/fusion_trace.json'])
    assert trace['states']['publish_outputs'] == 'failed'
    assert sum(v == 'executed' for v in trace['states'].values()) == 6
    assert 'is not in the subpath' in trace['events'][-1]['error']
    assert 'published/publish_outputs/records.csv' in old['_snapshot']
    assert 'artifacts/publish_outputs_bundle.json' not in old['_snapshot']
    corrected = tmp_path / 'corrected'; corrected.mkdir()
    corrected_alias = tmp_path / 'corrected_alias'; corrected_alias.symlink_to(corrected, target_is_directory=True)
    new = run_scripts(runner.public, value, profile, inputs, corrected_alias, tmp_path / 'new_scripts')
    checked = runner.frozen_v2_1.oracle.check(new, value, inputs, profile, {})
    assert checked['pass'], checked


def test_publisher_returns_same_relative_names_for_canonical_and_alias_roots(tmp_path):
    bundle = {'records': [{'id': 'one'}], 'counts': {'published_rows': 1}, 'source_sha256': {}, 'manifest_sha256': 'synthetic'}
    profile = {'fields': {'record_id': 'id'}}
    real = tmp_path / 'real'; real.mkdir()
    alias = tmp_path / 'alias'; alias.symlink_to(real, target_is_directory=True)
    a = runner.public.ops.publish(bundle, profile, real, 'canonical')
    b = runner.public.ops.publish(bundle, profile, alias, 'through_alias')
    assert a['published_files']['csv'] == 'published/canonical/records.csv'
    assert b['published_files']['csv'] == 'published/through_alias/records.csv'
    with pytest.raises(ValueError, match='overwrite'): runner.public.ops.publish(bundle, profile, alias, 'through_alias')
    with pytest.raises(ValueError, match='escapes'): runner.public.ops.publish(bundle, profile, alias, '../escape')


def test_outside_directory_symlink_is_still_rejected(tmp_path):
    root, outside = tmp_path / 'root', tmp_path / 'outside'
    root.mkdir(); outside.mkdir(); (root / 'published').symlink_to(outside, target_is_directory=True)
    bundle = {'records': [], 'counts': {}, 'source_sha256': {}, 'manifest_sha256': 'test'}
    with pytest.raises(ValueError, match='escapes'):
        runner.public.ops.publish(bundle, {'fields': {'record_id': 'id'}}, root, 'publisher')
    assert not list(outside.iterdir())


def test_production_public_validator_executes_through_symlinked_temporary_paths(tmp_path, monkeypatch):
    workspace, value = examples.public_workspace(tmp_path)
    contract = json.loads((workspace / 'v2_contract.json').read_text()); contract['version'] = runner.public.VERSION
    (workspace / 'v2_contract.json').write_text(json.dumps(contract))
    nominal = workspace / 'fixtures/scenarios/nominal'
    import shutil
    shutil.rmtree(nominal); examples.fixtures(nominal, examples.profile())
    submission = workspace / 'submission'; submission.mkdir()
    (submission / 'serviceflow.yaml').write_text(json.dumps(value))
    runner.public.compile_submission(workspace, submission)
    original_directory = tempfile.TemporaryDirectory
    aliases = []
    class AliasDirectory:
        def __init__(self, *args, **kwargs):
            self.holder = original_directory(*args, **kwargs)
            real = Path(self.holder.name).resolve()
            self.alias = real.parent / (real.name + '_symlink_test')
            self.alias.symlink_to(real, target_is_directory=True)
            self.name = str(self.alias); aliases.append(self.name)
        def __enter__(self): return self.name
        def __exit__(self, *args):
            self.alias.unlink(missing_ok=True); self.holder.cleanup()
    # The production validator and executor share this stdlib module. Forcing
    # aliases exercises the actual temporary-workspace argument used by jobs,
    # rather than only the earlier direct-script/static-validation tests.
    with monkeypatch.context() as scope:
        scope.setattr(tempfile, 'TemporaryDirectory', AliasDirectory)
        report = runner.public.validate_submission(workspace, submission, run_execution=True)
    assert aliases
    assert report['overall_status'] == 'pass', report
    assert all(g['status'] == 'pass' for g in report['gates'])
    g6 = next(g for g in report['gates'] if g['gate'] == 'G6-Exec')
    assert len(g6['details']['scenarios'][0]['executed_tasks']) == 7


def test_only_publisher_entry_normalization_changes_kernel_source():
    previous = Path(runner.public.fusion_ops.__file__).read_text()
    corrected = runner.public.fixed_source(previous)
    inserted = '    workspace = Path(workspace).resolve()\n'
    assert corrected == previous.replace('def publish(bundle, profile, workspace, intent):\n',
                                         'def publish(bundle, profile, workspace, intent):\n' + inserted, 1)
    assert runner.public.fixed_source(corrected) == corrected
    assert runner.frozen_v2_1.public.VERSION == 'p2sf.public-relational-methods/1'
    assert runner.public.VERSION == 'p2sf.public-relational-methods/2'


def test_job_stderr_contains_public_stage_failure_reason(tmp_path):
    profile, value = examples.profile(), examples.ir()
    inputs = tmp_path / 'inputs'; examples.fixtures(inputs, profile)
    data = json.loads((inputs / 'events.json').read_text()); data[0].pop(profile['fields']['join_key'])
    (inputs / 'events.json').write_text(json.dumps(data))
    raw = run_scripts(runner.public, value, profile, inputs, tmp_path / 'execution', tmp_path / 'scripts')
    assert any('Missing identity/join key' in e for e in raw['_errors'])


def test_image_payload_has_fixed_kernel_and_no_evaluator(tmp_path):
    agent = runner.agent_module(); context = tmp_path / 'image'
    agent.prepare_image_context(context)
    sources = context / 'v2'
    assert 'workspace = Path(workspace).resolve()' in (sources / 'fusion_ops.py').read_text()
    assert not any('oracle' in p.name for p in sources.iterdir())
    code = 'import sys;sys.path.insert(0,sys.argv[2]);sys.path.insert(0,sys.argv[1]);import semantic_public_tools as p;assert p.VERSION=="p2sf.public-relational-methods/2";assert "Path(workspace).resolve()" in p.deployment_sources()["fusion_ops"]'
    result = subprocess.run([sys.executable, '-c', code, str(sources), str(context / 'pkg/src')], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert agent.M5_VERSION == 'v2.28.2'
