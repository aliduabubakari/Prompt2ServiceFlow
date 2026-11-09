"""Offline design checks for the new serving configuration."""
import copy
import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('reasoning_generation', ROOT / 'scripts/run_v2_reasoning_generation.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def design():
    return pilot.replay.read_json(pilot.CONFIG)


def test_only_reasoning_control_changes_and_input_is_not_mutated():
    baseline = {key: {'model': 'same', 'messages': [{'role': 'user', 'content': 'same task'}],
                      'max_tokens': 16384, 'seed': 101, 'temperature': .2, 'top_p': 1}
                for key in design()['conditions']}
    original = copy.deepcopy(baseline)
    changed = pilot.build_requests(design(), baseline)
    assert baseline == original
    for key, request in changed.items():
        assert request.pop('reasoning_effort') == 'none'
        assert request == baseline[key]


@pytest.mark.parametrize('mutation', ['override', 'budget', 'conditions', 'baseline_control'])
def test_rejects_design_drift(mutation):
    d = design()
    baseline = {key: {} for key in d['conditions']}
    if mutation == 'override': d['request_override'] = {'reasoning_effort': 'low'}
    if mutation == 'budget': d['maximum_inference_requests'] = 3
    if mutation == 'conditions': d['conditions'] = ['compact_ir_json', 'full_ir_json']
    if mutation == 'baseline_control': baseline['full_ir_json']['reasoning_effort'] = 'none'
    with pytest.raises(ValueError): pilot.build_requests(d, baseline)


def evidence():
    return {'status': 'complete', 'source_inputs_unchanged': True, 'results': {
        'server_default': {'probe_success': True, 'reasoning_character_counts': {'reasoning': 239}},
        'reasoning_effort_none': {'probe_success': True, 'reasoning_character_counts': {'reasoning': 0}}}}


def test_requires_observed_control_effect():
    pilot.check_probe(evidence())


@pytest.mark.parametrize('mutation', ['parent_state', 'input_change', 'json_failure', 'reasoning_remains', 'no_default_reasoning'])
def test_rejects_missing_probe_evidence(mutation):
    r = evidence()
    if mutation == 'parent_state': r['status'] = 'complete_with_errors'
    if mutation == 'input_change': r['source_inputs_unchanged'] = False
    if mutation == 'json_failure': r['results']['reasoning_effort_none']['probe_success'] = False
    if mutation == 'reasoning_remains': r['results']['reasoning_effort_none']['reasoning_character_counts']['reasoning'] = 1
    if mutation == 'no_default_reasoning': r['results']['server_default']['reasoning_character_counts'] = {}
    with pytest.raises(ValueError): pilot.check_probe(r)
