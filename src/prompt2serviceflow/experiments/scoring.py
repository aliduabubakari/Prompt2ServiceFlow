"""Private gold-relative submission scoring (evaluation-side only).

Implements the private half of the validator split in
``plan_experiement_evals.md`` Sections 6-8. ``score_submission`` runs after a
method finishes and combines:

1. **Public-gate re-run (drift check):** the same ``validate_submission``
   implementation the method saw, re-run over the submission in its workspace.
2. **Graph recovery (RQ2):** alignment of submission intents to gold intents
   (service identity, source-step refs, category, I/O signatures), node/edge
   precision-recall-F1, over/under-decomposition, source-step coverage against
   the private internal spec, and an alignment-based edit distance.
3. **Binding accuracy (RQ3/E4):** top-1 accuracy, service-version correctness,
   and distractor confusion against the private candidate labels
   (semantic/target/contract/format mismatch, missing output, policy
   incompatible, generic escape hatch), plus invented-service
   (hallucination) and deprecated/incompatible selection rates.
4. **Artifact wiring:** producer-consumer intent-pair F1 via the alignment.
5. **G6-Assert:** gold assertion evaluation on scenario execution outputs.
   Executability (G6-Exec) stays in the public validator; assertion outcomes
   exist only here.

This module is evaluation-side tooling. It is never installed into submission
workspaces, and it reads gold artifacts, candidate labels, and internal specs
freely. Ranked-list metrics (MRR) are not part of the submission contract and
are reported as null.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from prompt2serviceflow.experiments.submission import (
    _SubmissionContext,
    _assemble_virtual_instance,
    validate_submission,
)
from prompt2serviceflow.validators.instance_validation import (
    _catalog_index,
    _evaluate_assertion,
    _execute_scenarios,
    _restore_snapshot,
)
from prompt2serviceflow.validators.schema_validation import load_document

TOOL_NAME = "score_submission"
TOOL_VERSION = "1.2.1"
REPORT_VERSION = "0.3.1"

REPO_ROOT = Path(__file__).resolve().parents[3]

# Alignment weights (sum to 1.0). Service identity and source-step overlap
# dominate; category and I/O signatures break ties.
ALIGNMENT_WEIGHT_SERVICE = 0.45
ALIGNMENT_WEIGHT_SOURCE_STEPS = 0.35
ALIGNMENT_WEIGHT_CATEGORY = 0.10
ALIGNMENT_WEIGHT_IO_SIGNATURE = 0.10
ALIGNMENT_THRESHOLD = 0.20

ESCAPE_HATCH_LABEL = "generic_escape_hatch"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seq(value: Any) -> list[Any]:
    """Tolerate null/missing collections in model-emitted documents."""
    return value if isinstance(value, list) else []


def _bound_services(serviceflow: dict[str, Any]) -> dict[str, tuple[str, str]]:
    return {
        binding["intent_id"]: (binding["service_id"], binding["service_version"])
        for binding in _seq(serviceflow.get("bindings"))
        if isinstance(binding, dict) and "intent_id" in binding
    }


def _io_signature(serviceflow: dict[str, Any], intent_id: str) -> set[str]:
    artifacts = {
        item["artifact_id"]: item
        for item in _seq(serviceflow.get("artifacts"))
        if isinstance(item, dict) and "artifact_id" in item
    }
    intent = next(
        (
            item
            for item in _seq(serviceflow.get("service_intents"))
            if item["intent_id"] == intent_id
        ),
        None,
    )
    if intent is None:
        return set()
    signature: set[str] = set()
    for artifact_id in [*_seq(intent.get("inputs")), *_seq(intent.get("outputs"))]:
        artifact = artifacts.get(artifact_id)
        if artifact is not None:
            signature.add(artifact["data_type"])
    return signature


def _jaccard(left: Iterable[Any], right: Iterable[Any]) -> float:
    left_set, right_set = set(left), set(right)
    if not left_set and not right_set:
        return 0.0
    union = left_set | right_set
    if not union:
        return 0.0
    return len(left_set & right_set) / len(union)


def _alignment_score(
    submission_intent: dict[str, Any],
    gold_intent: dict[str, Any],
    submission: dict[str, Any],
    gold: dict[str, Any],
    catalog: dict[tuple[str, str], dict[str, Any]],
) -> float:
    submission_bound = _bound_services(submission)
    gold_bound = _bound_services(gold)
    score = 0.0
    sub_service = submission_bound.get(submission_intent["intent_id"])
    gold_service = gold_bound.get(gold_intent["intent_id"])
    if sub_service is not None and sub_service == gold_service:
        score += ALIGNMENT_WEIGHT_SERVICE
    score += ALIGNMENT_WEIGHT_SOURCE_STEPS * _jaccard(
        _seq(submission_intent.get("source_step_refs")),
        _seq(gold_intent.get("source_step_refs")),
    )
    if sub_service is not None and gold_service is not None:
        sub_descriptor = catalog.get(sub_service)
        gold_descriptor = catalog.get(gold_service)
        if (
            sub_descriptor is not None
            and gold_descriptor is not None
            and sub_descriptor["category"] == gold_descriptor["category"]
        ):
            score += ALIGNMENT_WEIGHT_CATEGORY
    score += ALIGNMENT_WEIGHT_IO_SIGNATURE * _jaccard(
        _io_signature(submission, submission_intent["intent_id"]),
        _io_signature(gold, gold_intent["intent_id"]),
    )
    return score


def _align_intents(
    submission: dict[str, Any],
    gold: dict[str, Any],
    catalog: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, str]:
    """Greedy deterministic assignment of submission intents to gold intents."""
    candidates: list[tuple[float, str, str]] = []
    for submission_intent in _seq(submission.get("service_intents")):
        for gold_intent in _seq(gold.get("service_intents")):
            score = _alignment_score(submission_intent, gold_intent, submission, gold, catalog)
            if score >= ALIGNMENT_THRESHOLD:
                candidates.append((score, submission_intent["intent_id"], gold_intent["intent_id"]))
    # Deterministic: score desc, then lexicographic ids.
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    alignment: dict[str, str] = {}
    used_gold: set[str] = set()
    for score, submission_id, gold_id in candidates:
        if submission_id in alignment or gold_id in used_gold:
            continue
        alignment[submission_id] = gold_id
        used_gold.add(gold_id)
    return alignment


def _pair_metrics(
    true_positives: int, false_positives: int, false_negatives: int
) -> dict[str, float]:
    precision = (
        true_positives / (true_positives + false_positives)
        if true_positives + false_positives
        else 0.0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if true_positives + false_negatives
        else 0.0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def _edge_metrics(
    submission: dict[str, Any],
    gold: dict[str, Any],
    alignment: dict[str, str],
) -> dict[str, Any]:
    gold_edges = {(edge["from"], edge["to"]) for edge in _seq(gold["control_flow"].get("edges"))}
    submission_edges = {
        (edge["from"], edge["to"])
        for edge in _seq(submission["control_flow"].get("edges"))
        if isinstance(edge, dict) and "from" in edge and "to" in edge
    }
    mapped_submission_edges: set[tuple[str, str]] = set()
    unaligned_submission_edges = 0
    for source, target in submission_edges:
        if source in alignment and target in alignment:
            mapped_submission_edges.add((alignment[source], alignment[target]))
        else:
            unaligned_submission_edges += 1
    true_positives = len(mapped_submission_edges & gold_edges)
    false_positives = len(mapped_submission_edges - gold_edges) + unaligned_submission_edges
    # ``gold_edges - mapped_submission_edges`` already includes relations with
    # an unaligned endpoint. Adding those again would double-count false
    # negatives and artificially depress recall/F1.
    false_negatives = len(gold_edges - mapped_submission_edges)
    metrics = _pair_metrics(true_positives, false_positives, false_negatives)
    metrics["true_positives"] = true_positives
    metrics["false_positives"] = false_positives
    metrics["false_negatives"] = false_negatives
    return metrics


def _wiring_pairs(serviceflow: dict[str, Any]) -> set[tuple[str, str]]:
    consumers: dict[str, list[str]] = {}
    for intent in _seq(serviceflow.get("service_intents")):
        for artifact_id in _seq(intent.get("inputs")):
            consumers.setdefault(artifact_id, []).append(intent["intent_id"])
    pairs: set[tuple[str, str]] = set()
    for artifact in _seq(serviceflow.get("artifacts")):
        producer = artifact["producer"]
        producers = (
            [] if producer is None else producer if isinstance(producer, list) else [producer]
        )
        for producer_id in producers:
            for consumer_id in consumers.get(artifact.get("artifact_id"), []):
                pairs.add((producer_id, consumer_id))
    return pairs


def _wiring_metrics(
    submission: dict[str, Any],
    gold: dict[str, Any],
    alignment: dict[str, str],
) -> dict[str, Any]:
    gold_pairs = _wiring_pairs(gold)
    mapped: set[tuple[str, str]] = set()
    unaligned_submission_pairs = 0
    for source, target in _wiring_pairs(submission):
        if source in alignment and target in alignment:
            mapped.add((alignment[source], alignment[target]))
        else:
            unaligned_submission_pairs += 1
    true_positives = len(mapped & gold_pairs)
    false_positives = len(mapped - gold_pairs) + unaligned_submission_pairs
    false_negatives = len(gold_pairs - mapped)
    if not gold_pairs and not mapped and not unaligned_submission_pairs:
        return {
            "status": "not_applicable",
            "reason": "gold and submission contain no producer-consumer wiring pairs",
            "applicable": False,
            "precision": None,
            "recall": None,
            "f1": None,
            "true_positives": 0,
            "false_positives": 0,
            "false_negatives": 0,
        }
    metrics = _pair_metrics(true_positives, false_positives, false_negatives)
    metrics["applicable"] = True
    metrics["true_positives"] = true_positives
    metrics["false_positives"] = false_positives
    metrics["false_negatives"] = false_negatives
    return metrics


# ---------------------------------------------------------------------------
# Section scorers
# ---------------------------------------------------------------------------


def _score_graph(
    submission: dict[str, Any],
    gold: dict[str, Any],
    catalog: dict[tuple[str, str], dict[str, Any]],
    internal_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    alignment = _align_intents(submission, gold, catalog)
    submission_count = len(_seq(submission.get("service_intents")))
    gold_count = len(_seq(gold.get("service_intents")))
    matched = len(alignment)
    node_metrics = _pair_metrics(matched, submission_count - matched, gold_count - matched)
    edge_metrics = _edge_metrics(submission, gold, alignment)
    unmatched_submission = submission_count - matched
    unmatched_gold = gold_count - matched
    result: dict[str, Any] = {
        "alignment": {
            "method": "greedy(service=0.45, source_steps=0.35, category=0.10, io=0.10), "
            f"threshold={ALIGNMENT_THRESHOLD}",
            "matched": matched,
            "submission_intents": submission_count,
            "gold_intents": gold_count,
            "mapping": dict(sorted(alignment.items())),
        },
        "node": {**node_metrics, "matched": matched},
        "edge": edge_metrics,
        "over_decomposition_rate": max(0, submission_count - gold_count) / gold_count
        if gold_count
        else 0.0,
        "under_decomposition_rate": max(0, gold_count - submission_count) / gold_count
        if gold_count
        else 0.0,
        "alignment_edit_distance": (
            unmatched_submission
            + unmatched_gold
            + edge_metrics["false_positives"]
            + edge_metrics["false_negatives"]
        ),
    }
    if internal_spec is not None:
        spec_steps = {item["step_id"] for item in internal_spec["steps"]}
        accounted = {
            ref
            for intent in _seq(submission.get("service_intents"))
            for ref in _seq(intent.get("source_step_refs"))
        }
        accounted |= {
            item["source_step_ref"] for item in _seq(submission.get("source_step_accounting"))
        }
        result["source_step_coverage"] = {
            "covered": len(spec_steps & accounted),
            "total": len(spec_steps),
            "rate": len(spec_steps & accounted) / len(spec_steps) if spec_steps else 0.0,
            "missing": sorted(spec_steps - accounted),
            "unknown_refs": sorted(accounted - spec_steps),
        }
    return result


def _score_bindings(
    submission: dict[str, Any],
    gold: dict[str, Any],
    alignment: dict[str, str],
    candidate_labels: dict[str, Any],
    catalog: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    submission_bound = _bound_services(submission)
    gold_bound = _bound_services(gold)
    gold_to_submission = {gold_id: sub_id for sub_id, gold_id in alignment.items()}
    label_sets = {item["required_service_id"]: item for item in candidate_labels["candidate_sets"]}

    per_intent: list[dict[str, Any]] = []
    confusion_by_label: dict[str, int] = {}
    correct = 0
    version_correct = 0
    evaluated = 0
    invented = 0
    escape_hatch = 0
    deprecated = 0
    for gold_intent_id, (gold_service, gold_version) in sorted(gold_bound.items()):
        evaluated += 1
        submission_intent_id = gold_to_submission.get(gold_intent_id)
        entry: dict[str, Any] = {
            "gold_intent": gold_intent_id,
            "gold_service": gold_service,
            "submission_intent": submission_intent_id,
        }
        if submission_intent_id is None:
            entry["outcome"] = "missing_intent"
            confusion_by_label["missing_intent"] = confusion_by_label.get("missing_intent", 0) + 1
            per_intent.append(entry)
            continue
        submission_service = submission_bound.get(submission_intent_id)
        entry["submission_service"] = submission_service[0] if submission_service else None
        if submission_service is not None and submission_service[0] == gold_service:
            correct += 1
            entry["outcome"] = "correct"
            if submission_service[1] == gold_version:
                version_correct += 1
                entry["version_correct"] = True
            else:
                entry["version_correct"] = False
            per_intent.append(entry)
            continue
        if submission_service is None:
            entry["outcome"] = "unbound"
            confusion_by_label["unbound"] = confusion_by_label.get("unbound", 0) + 1
            per_intent.append(entry)
            continue
        descriptor = catalog.get(submission_service)
        if descriptor is None:
            entry["outcome"] = "invented_service"
            invented += 1
            confusion_by_label["invented_service"] = (
                confusion_by_label.get("invented_service", 0) + 1
            )
            per_intent.append(entry)
            continue
        label_set = label_sets.get(gold_service)
        label = label_set["labels"].get(submission_service[0]) if label_set else None
        if label is not None:
            entry["outcome"] = label
            confusion_by_label[label] = confusion_by_label.get(label, 0) + 1
            if label == ESCAPE_HATCH_LABEL:
                escape_hatch += 1
        elif descriptor["lifecycle"]["status"] != "active":
            entry["outcome"] = "deprecated_incompatible"
            deprecated += 1
            confusion_by_label["deprecated_incompatible"] = (
                confusion_by_label.get("deprecated_incompatible", 0) + 1
            )
        else:
            entry["outcome"] = "out_of_candidate_set"
            confusion_by_label["out_of_candidate_set"] = (
                confusion_by_label.get("out_of_candidate_set", 0) + 1
            )
        per_intent.append(entry)

    aligned_pairs = sum(1 for item in per_intent if item["submission_intent"] is not None)
    return {
        "top1_accuracy": correct / evaluated if evaluated else 0.0,
        "aligned_accuracy": correct / aligned_pairs if aligned_pairs else 0.0,
        "version_accuracy_given_correct_service": (version_correct / correct if correct else None),
        "mean_reciprocal_rank": None,
        "mrr_note": "ranked candidate outputs are not part of the submission contract",
        "evaluated_gold_bindings": evaluated,
        "correct": correct,
        "confusion_by_label": dict(sorted(confusion_by_label.items())),
        "rates": {
            "invented_service": invented / evaluated if evaluated else 0.0,
            "generic_escape_hatch": escape_hatch / evaluated if evaluated else 0.0,
            "deprecated_incompatible": deprecated / evaluated if evaluated else 0.0,
        },
        "per_intent": per_intent,
    }


def _score_g6_assert(
    instance_dir: Path,
    workspace_dir: Path,
    submission_dir: Path,
) -> dict[str, Any]:
    assertions_path = instance_dir / "gold" / "assertions.yaml"
    assertions_document = load_document(assertions_path)
    assertion_sets = {
        item["scenario"]: item["assertions"] for item in assertions_document["scenarios"]
    }
    context = _SubmissionContext(workspace_dir, submission_dir)
    if not context.manifest_path.is_file():
        return {"status": "unscored", "reason": "submission runtime manifest missing"}
    try:
        context.manifest = load_document(context.manifest_path)
    except Exception as exc:
        return {"status": "unscored", "reason": f"runtime manifest does not parse: {exc}"}

    scenario_reports: list[dict[str, Any]] = []
    total = 0
    passed = 0
    with tempfile.TemporaryDirectory(prefix="p2sf-assert-") as temp:
        try:
            instance = _assemble_virtual_instance(context, Path(temp))
            execution_results = _execute_scenarios(
                instance, context.manifest, sandbox_generated=True
            )
        except Exception as exc:
            return {"status": "unscored", "reason": f"scenario execution failed: {exc}"}
        execution_names = [result["scenario"] for result in execution_results]
        assertion_names = list(assertion_sets)
        scenario_aliases: dict[str, str] = {}
        # Historical Main-40 packages name their sole reviewed assertion
        # scenario ``run``, while the deterministic submission compiler names
        # the same sole fixture scenario ``nominal``.  A one-to-one mismatch
        # is unambiguous and can be evaluated by position.  Every other name
        # mismatch remains a fail-closed scoring error.
        if (
            len(execution_names) == 1
            and len(assertion_names) == 1
            and execution_names[0] != assertion_names[0]
        ):
            scenario_aliases[execution_names[0]] = assertion_names[0]
        unmatched_execution = [
            name
            for name in execution_names
            if name not in assertion_sets and name not in scenario_aliases
        ]
        matched_assertion_names = {
            scenario_aliases.get(name, name)
            for name in execution_names
            if name in assertion_sets or name in scenario_aliases
        }
        unmatched_assertions = [
            name for name in assertion_names if name not in matched_assertion_names
        ]
        for result in execution_results:
            errors = result.pop("_errors")
            snapshot = result.pop("_snapshot")
            result.pop("assertions", None)
            scenario = result["scenario"]
            report: dict[str, Any] = {
                "scenario": scenario,
                "execution_status": "pass" if not errors else "fail",
                "execution_errors": errors,
                "assertions": [],
            }
            with tempfile.TemporaryDirectory(prefix=f"p2sf-assert-{scenario}-") as restore_temp:
                workspace = Path(restore_temp)
                _restore_snapshot(snapshot, workspace)
                assertion_scenario = scenario_aliases.get(scenario, scenario)
                for assertion in assertion_sets.get(assertion_scenario, []):
                    total += 1
                    if errors:
                        status, message = "error", "scenario execution failed"
                    else:
                        try:
                            ok, message = _evaluate_assertion(assertion, workspace)
                            status = "pass" if ok else "fail"
                        except Exception as exc:
                            status = "fail"
                            message = f"assertion evaluation error: {exc}"
                    passed += int(status == "pass")
                    report["assertions"].append(
                        {
                            "assertion_id": assertion["assertion_id"],
                            "status": status,
                            "message": message,
                        }
                    )
            report["status"] = (
                "pass"
                if not errors and all(item["status"] == "pass" for item in report["assertions"])
                else "fail"
            )
            if assertion_scenario != scenario:
                report["assertion_scenario"] = assertion_scenario
                report["scenario_alias_applied"] = True
            if scenario in unmatched_execution:
                report["status"] = "fail"
                report["scoring_error"] = "no reviewed assertion set matches this scenario"
            scenario_reports.append(report)
    expected_total = sum(len(items) for items in assertion_sets.values())
    if unmatched_assertions:
        total += sum(len(assertion_sets[name]) for name in unmatched_assertions)
    return {
        "scenarios": scenario_reports,
        "assertions_total": total,
        "assertions_passed": passed,
        "pass_rate": passed / total if total else None,
        "expected_assertions_total": expected_total,
        "scenario_aliases": scenario_aliases,
        "unmatched_execution_scenarios": unmatched_execution,
        "unmatched_assertion_scenarios": unmatched_assertions,
        "overall_status": (
            "pass"
            if scenario_reports
            and not unmatched_execution
            and not unmatched_assertions
            and total > 0
            and all(item["status"] == "pass" for item in scenario_reports)
            else "fail"
        ),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_submission(
    instance_dir: Path,
    workspace_dir: Path,
    submission_dir: Path | None = None,
    *,
    run_execution: bool = True,
) -> dict[str, Any]:
    instance_dir = instance_dir.resolve()
    workspace_dir = workspace_dir.resolve()
    submission_dir = (submission_dir or workspace_dir / "submission").resolve()

    # 1. Public-gate re-run (drift check: same implementation the method saw).
    public_report = validate_submission(workspace_dir, submission_dir, run_execution=run_execution)

    # 2. Gold-relative scoring.
    gold = load_document(instance_dir / "gold" / "serviceflow.yaml")
    candidate_labels = load_document(instance_dir / "gold" / "candidate_labels.yaml")
    catalog = _catalog_index(workspace_dir / "catalog")
    internal_spec: dict[str, Any] | None = None
    internal_spec_path = gold["source"].get("internal_spec_path")
    if internal_spec_path:
        candidate = (REPO_ROOT / "benchmark" / internal_spec_path).resolve()
        if candidate.is_file():
            internal_spec = load_document(candidate)

    submission: dict[str, Any] | None = None
    serviceflow_path = submission_dir / "serviceflow.yaml"
    if serviceflow_path.is_file():
        try:
            submission = load_document(serviceflow_path)
            if not isinstance(submission, dict) or "service_intents" not in submission:
                submission = None
        except Exception:
            submission = None

    sections: dict[str, Any] = {}
    if submission is None:
        unscored = {"status": "unscored", "reason": "no parseable submission ServiceFlowIR"}
        sections = {"graph": unscored, "binding": unscored, "wiring": unscored}
    else:
        try:
            alignment = _align_intents(submission, gold, catalog)
            sections["graph"] = _score_graph(submission, gold, catalog, internal_spec)
            sections["binding"] = _score_bindings(
                submission, gold, alignment, candidate_labels, catalog
            )
            sections["wiring"] = _wiring_metrics(submission, gold, alignment)
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            # A schema-invalid model output is an experimental failure, not a
            # harness failure. Preserve it in unconditional denominators.
            unscored = {
                "status": "unscored",
                "reason": f"malformed submission structure: {exc}",
            }
            sections = {"graph": unscored, "binding": unscored, "wiring": unscored}

    if run_execution:
        sections["g6_assert"] = _score_g6_assert(instance_dir, workspace_dir, submission_dir)
    else:
        sections["g6_assert"] = {"status": "skipped", "reason": "execution disabled (--no-exec)"}

    public_pass = public_report["overall_status"] == "pass"
    assert_section = sections["g6_assert"]
    assert_pass = assert_section.get("overall_status") == "pass"
    graph_section = sections["graph"]
    binding_section = sections["binding"]
    wiring_section = sections["wiring"]
    summary = {
        "public_gates_status": public_report["overall_status"],
        "first_failing_gate": public_report["first_failing_gate"],
        "g6_assert_status": assert_section.get("overall_status", assert_section.get("status")),
        "full_pass_g0_g6": (public_pass and assert_pass) if run_execution else None,
        "node_f1": graph_section.get("node", {}).get("f1") if "node" in graph_section else None,
        "edge_f1": graph_section.get("edge", {}).get("f1") if "edge" in graph_section else None,
        "binding_top1_accuracy": (
            binding_section.get("top1_accuracy") if "top1_accuracy" in binding_section else None
        ),
        "binding_version_accuracy": (
            binding_section.get("version_accuracy")
            if "version_accuracy" in binding_section
            else None
        ),
        "wiring_f1": wiring_section.get("f1") if "f1" in wiring_section else None,
        "wiring_applicable": wiring_section.get("applicable"),
        "alignment_edit_distance": graph_section.get("alignment_edit_distance"),
        "over_decomposition_rate": graph_section.get("over_decomposition_rate"),
        "under_decomposition_rate": graph_section.get("under_decomposition_rate"),
        "source_step_coverage": (graph_section.get("source_step_coverage") or {}).get("rate"),
        "g6_assert_pass_rate": assert_section.get("pass_rate"),
    }
    return {
        "report_version": REPORT_VERSION,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "instance": str(instance_dir),
        "workspace": str(workspace_dir),
        "submission": str(submission_dir),
        "summary": summary,
        "public_gates": public_report,
        "graph": sections["graph"],
        "binding": sections["binding"],
        "wiring": sections["wiring"],
        "g6_assert": sections["g6_assert"],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _score_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="score_submission",
        description="Private gold-relative submission scoring (evaluation-side only).",
    )
    parser.add_argument(
        "--instance", type=Path, required=True, help="benchmark instance dir (private)"
    )
    parser.add_argument("--workspace", type=Path, required=True, help="public workspace dir")
    parser.add_argument(
        "--submission",
        type=Path,
        default=None,
        help="submission dir (default: <workspace>/submission)",
    )
    parser.add_argument("--out", type=Path, default=None, help="write the JSON report here")
    parser.add_argument("--no-exec", action="store_true", help="skip execution-based scoring")
    parser.add_argument("--quiet", action="store_true", help="print only the summary block")
    return parser.parse_args(argv)


def score_main(argv: list[str] | None = None) -> int:
    args = _score_args(argv)
    report = score_submission(
        args.instance, args.workspace, args.submission, run_execution=not args.no_exec
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.quiet:
        print(json.dumps(report["summary"], indent=2))
    else:
        print(json.dumps(report["summary"], indent=2))
        print(f"full_pass_g0_g6: {report['summary']['full_pass_g0_g6']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(score_main())
