"""Regression tests for gold-relative edge and artifact-wiring metrics."""

from prompt2serviceflow.experiments.scoring import _edge_metrics, _wiring_metrics


def test_unaligned_gold_edge_counts_one_false_negative() -> None:
    gold = {"control_flow": {"edges": [{"from": "a", "to": "b"}]}}
    submission = {"control_flow": {"edges": []}}
    metrics = _edge_metrics(submission, gold, {"submitted_a": "a"})
    assert metrics["false_negatives"] == 1
    assert metrics["recall"] == 0.0


def test_unaligned_gold_wiring_counts_one_false_negative() -> None:
    gold = {
        "service_intents": [
            {"intent_id": "a", "inputs": []},
            {"intent_id": "b", "inputs": ["artifact"]},
        ],
        "artifacts": [{"artifact_id": "artifact", "producer": "a"}],
    }
    submission = {
        "service_intents": [{"intent_id": "submitted_a", "inputs": []}],
        "artifacts": [],
    }
    metrics = _wiring_metrics(submission, gold, {"submitted_a": "a"})
    assert metrics["false_negatives"] == 1
    assert metrics["recall"] == 0.0
