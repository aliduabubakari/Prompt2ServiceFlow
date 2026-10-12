#!/usr/bin/env python3
"""Run frozen Prompt2ServiceFlow component ablations by benchmark split."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

from prompt2serviceflow.experiments.freeze import check_freeze  # noqa: E402
from prompt2serviceflow.experiments.harness import run_one  # noqa: E402
from prompt2serviceflow.experiments.leakage import scan_workspace_root  # noqa: E402
from prompt2serviceflow.experiments.llm import load_model_configs  # noqa: E402
from prompt2serviceflow.experiments.prompts import ABLATION_PROTOCOL_VERSION  # noqa: E402
from prompt2serviceflow.experiments.retrieval import (  # noqa: E402
    retrieve_candidate_document,
)


ABLATIONS = {
    "baseline_m2": {"method": "m2", "view": {}},
    "baseline_m3": {"method": "m3", "view": {}},
    "baseline_m4": {"method": "m4", "view": {}},
    "a1_no_contracts": {
        "method": "m4",
        "view": {
            "withhold_contracts": True,
            "strip_contract_details": True,
            "diagnostic_visibility": "gate_identity",
        },
    },
    "a2_no_policies": {
        "method": "m4",
        "view": {
            "withhold_policies": True,
            "strip_descriptor_fields": ["lifecycle"],
            "diagnostic_visibility": "gate_identity",
        },
    },
    "a3_no_g5_repair_feedback": {
        "method": "m4",
        "view": {"redact_diagnostic_gates": ["G5"]},
    },
    "a3_full_catalog_no_candidates": {
        "method": "m3",
        "view": {"withhold_candidates": True, "full_catalog": True},
    },
    "a4_no_distractors": {"method": "m3", "oracle_candidates": True},
    # This is intentionally registered as a bundled stage-removal contrast:
    # M2 receives the same public catalog, candidate, contract, and fixture
    # inputs, but emits executable Argo directly. It therefore removes the
    # ServiceFlowIR-centered assembly, deterministic projection, IR gates, and
    # IR-local repair together; results must not be attributed to IR alone.
    "a4_no_serviceflow_ir_stage": {"method": "m2", "view": {}},
    "a5_no_repair": {"method": "m3", "view": {}},
    "a6_unstructured_diagnostics": {
        "method": "m4",
        "view": {"diagnostic_visibility": "gate_identity"},
    },
    "a8_first_gate_targeting": {
        "method": "m4",
        "view": {"repair_targeting": "first_gate"},
    },
    "a9_no_execution_feedback": {"method": "m4", "repair_with_execution": False},
    "a10_bm25": {"method": "m3", "retrieval_strategy": "bm25"},
    "a10_embedding": {"method": "m3", "retrieval_strategy": "embedding"},
    "a10_hybrid": {"method": "m3", "retrieval_strategy": "hybrid"},
    "a10_oracle_candidates": {"method": "m3", "retrieval_strategy": "oracle"},
    "a11_name_description": {
        "method": "m4",
        "view": {"descriptor_profile": "name_description"},
    },
    "a11_plus_artifacts": {
        "method": "m4",
        "view": {"descriptor_profile": "artifacts"},
    },
    "a11_plus_parameters": {
        "method": "m4",
        "view": {"descriptor_profile": "parameters"},
    },
    "a11_plus_policies": {
        "method": "m4",
        "view": {"descriptor_profile": "policies"},
    },
    "a11_full_descriptor": {
        "method": "m4",
        "view": {"descriptor_profile": "full"},
    },
}

CONFIRMATORY_ABLATIONS = (
    "a1_no_contracts",
    "a2_no_policies",
    "a3_no_g5_repair_feedback",
    "a5_no_repair",
    "a6_unstructured_diagnostics",
)

SUPPORTED_ABLATION_PROTOCOL_VERSIONS = {"1.0.0", ABLATION_PROTOCOL_VERSION}


def _resume_design_mismatches(summary: dict, expected_design: dict) -> list[str]:
    """Compare immutable settings while accepting one legacy metadata omission.

    Early v24 batch summaries did not serialize ``retrieval_configuration`` even
    though it was fixed by the named freeze.  The omission is safe to backfill
    after every other immutable field (including ``freeze_id``) matches.
    """

    return [
        f"{key}: batch={summary.get(key)!r}, requested={value!r}"
        for key, value in expected_design.items()
        if not (key == "retrieval_configuration" and key not in summary)
        and summary.get(key) != value
    ]


class _CachedLMStudioEmbedder:
    def __init__(self, *, base_url: str, model: str) -> None:
        from openai import OpenAI

        self.client = OpenAI(api_key="lm-studio", base_url=base_url, timeout=600)
        self.model = model
        self.cache: dict[str, list[float]] = {}
        self.calls = 0
        self.texts_embedded = 0
        self.latency_s = 0.0

    def __call__(self, texts: list[str]) -> list[list[float]]:
        missing = list(dict.fromkeys(text for text in texts if text not in self.cache))
        if missing:
            started = time.monotonic()
            response = self.client.embeddings.create(model=self.model, input=missing)
            self.latency_s += time.monotonic() - started
            self.calls += 1
            self.texts_embedded += len(missing)
            ordered = sorted(response.data, key=lambda item: item.index)
            if len(ordered) != len(missing):
                raise RuntimeError("embedding endpoint returned the wrong vector count")
            self.cache.update((text, list(item.embedding)) for text, item in zip(missing, ordered))
        return [self.cache[text] for text in texts]

    def usage(self) -> dict:
        return {
            "model": self.model,
            "calls": self.calls,
            "texts_embedded": self.texts_embedded,
            "latency_s": round(self.latency_s, 3),
            "cache_entries": len(self.cache),
        }


def _write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _oracle_candidates(instance: Path, workspace: Path) -> str:
    public = yaml.safe_load(
        (workspace / "candidates/candidate_sets.yaml").read_text(encoding="utf-8")
    )
    labels = yaml.safe_load((instance / "gold/candidate_labels.yaml").read_text(encoding="utf-8"))
    required = {
        item["candidate_set_id"]: item["required_service_id"] for item in labels["candidate_sets"]
    }
    for item in public["candidate_sets"]:
        item["service_ids"] = [required[item["candidate_set_id"]]]
    # This rendered document is label-free: it contains the same public shape,
    # with distractors removed as the registered A4 intervention.
    return yaml.safe_dump(public, sort_keys=False)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="local-gpt-oss-20b")
    parser.add_argument("--ablations", nargs="*", default=list(CONFIRMATORY_ABLATIONS))
    parser.add_argument(
        "--split", choices=("main", "validation", "extension"), default="main"
    )
    parser.add_argument("--instances", nargs="*", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "experiments/config/models.json"
    )
    parser.add_argument(
        "--freeze-config", type=Path, default=PROJECT_ROOT / "experiments/config/freeze.json"
    )
    parser.add_argument("--runs-root", type=Path, default=PROJECT_ROOT / "experiments/runs")
    parser.add_argument("--batch-summary", type=Path, default=None, help="resume this batch")
    parser.add_argument("--allow-validation-rerun", action="store_true")
    parser.add_argument(
        "--workspaces-root", type=Path, default=PROJECT_ROOT / "experiments/workspaces"
    )
    parser.add_argument("--benchmark-root", type=Path, default=PROJECT_ROOT / "benchmark")
    parser.add_argument("--allow-unfrozen", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _args()
    load_dotenv(PROJECT_ROOT / ".env")
    roster = load_model_configs(args.config)
    if args.model not in roster:
        print(f"error: model {args.model!r} is not in the roster", file=sys.stderr)
        return 2
    if args.max_workers < 1:
        print("error: --max-workers must be at least 1", file=sys.stderr)
        return 2
    if args.samples < 1:
        print("error: --samples must be at least 1", file=sys.stderr)
        return 2
    if not args.allow_unfrozen and (args.instances or args.limit is not None):
        print("error: instance subsets/limits are pilot-only", file=sys.stderr)
        return 2
    unknown = sorted(set(args.ablations) - (set(ABLATIONS) | {"a7_repair_budget"}))
    if unknown:
        print(f"error: unknown ablations: {unknown}", file=sys.stderr)
        return 2
    freeze, errors = check_freeze(
        freeze_path=args.freeze_config,
        roster_path=args.config,
        repair_budget=3,
        model_id=args.model,
        require_frozen=not args.allow_unfrozen,
        max_workers=args.max_workers,
    )
    protocol_version = freeze.get("ablation_protocol_version")
    if protocol_version not in SUPPORTED_ABLATION_PROTOCOL_VERSIONS:
        errors.append(
            "unsupported ablation protocol version: "
            f"freeze={protocol_version!r}, "
            f"supported={sorted(SUPPORTED_ABLATION_PROTOCOL_VERSIONS)!r}"
        )
    frozen_conditions = (freeze.get("ablation") or {}).get("confirmatory_conditions")
    if not args.allow_unfrozen and list(args.ablations) != frozen_conditions:
        errors.append(
            "confirmatory ablations must exactly follow the frozen condition order"
        )
    frozen_samples = int(freeze.get("samples_per_instance", 1))
    if not args.allow_unfrozen and args.samples != frozen_samples:
        errors.append(
            f"sample count drift: freeze={frozen_samples!r}, run={args.samples!r}"
        )
    if errors and not args.allow_unfrozen:
        print(f"error: freeze mismatch: {'; '.join(errors)}", file=sys.stderr)
        return 1
    leakage = scan_workspace_root(args.workspaces_root)
    if leakage["status"] != "pass":
        print(f"error: leakage gate found {leakage['finding_count']} issues", file=sys.stderr)
        return 1

    validation_lock = args.runs_root / "ablation_validation_lock.json"
    if (
        args.split == "validation"
        and validation_lock.exists()
        and not args.batch_summary
        and not args.allow_validation_rerun
    ):
        print(f"error: Validation-20 ablation is locked by {validation_lock}", file=sys.stderr)
        return 1

    selected = []
    for workspace in sorted((args.workspaces_root / args.split).glob("*")):
        if not (workspace / "workspace.yaml").is_file():
            continue
        if args.instances and workspace.name not in args.instances:
            continue
        instance = args.benchmark_root / "instances" / args.split / workspace.name
        if instance.is_dir():
            selected.append((workspace, instance))
    if args.limit is not None:
        selected = selected[: args.limit]
    if not selected:
        print(f"error: no {args.split} instances selected", file=sys.stderr)
        return 2

    conditions: list[tuple[str, dict, int]] = []
    for ablation_id in args.ablations:
        if ablation_id == "a7_repair_budget":
            for budget in (0, 1, 2, 3):
                conditions.append(
                    (
                        f"a7_repair_budget_{budget}",
                        {
                            "method": "m4",
                            "view": {},
                            "repair_budget": budget,
                        },
                        budget,
                    )
                )
        else:
            spec = dict(ABLATIONS[ablation_id])
            conditions.append((ablation_id, spec, 3))

    sample_seeds = list((freeze.get("decoding") or {}).get("sample_seeds") or [])
    if len(sample_seeds) < args.samples:
        print(
            f"error: freeze declares {len(sample_seeds)} sample seeds for {args.samples} samples",
            file=sys.stderr,
        )
        return 2
    sample_seeds = [int(seed) for seed in sample_seeds[: args.samples]]

    retrieval_config = freeze.get("retrieval") or {}
    needs_embeddings = any(
        spec.get("retrieval_strategy") in {"embedding", "hybrid"} for _, spec, _ in conditions
    )
    embedder = (
        _CachedLMStudioEmbedder(
            base_url=freeze["endpoint"]["base_url"],
            model=retrieval_config["embedding_model"],
        )
        if needs_embeddings
        else None
    )

    instance_ids = [workspace.name for workspace, _ in selected]
    if args.batch_summary:
        summary_path = args.batch_summary.resolve()
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: cannot resume batch summary: {exc}", file=sys.stderr)
            return 2
        expected_design = {
            "freeze_id": freeze["freeze_id"],
            "ablation_protocol_version": protocol_version,
            "model": args.model,
            "split": args.split,
            "instances": instance_ids,
            "ablations": args.ablations,
            "samples_per_instance": args.samples,
            "sample_seeds": sample_seeds,
            "max_workers": args.max_workers,
            "retrieval_configuration": retrieval_config,
        }
        mismatches = _resume_design_mismatches(summary, expected_design)
        if mismatches:
            print(
                "error: resume arguments do not match immutable ablation design: "
                + "; ".join(mismatches),
                file=sys.stderr,
            )
            return 2
        if "retrieval_configuration" not in summary:
            summary["retrieval_configuration"] = retrieval_config
            _write_json(summary_path, summary)
        batch_id = summary["batch_id"]
    else:
        batch_id = (
            f"ablations__{args.model}__"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}__"
            f"{uuid.uuid4().hex[:8]}"
        )
        summary_path = args.runs_root / f"{batch_id}.json"
        summary = {
            "status": "running",
            "batch_id": batch_id,
            "freeze_id": freeze["freeze_id"],
            "ablation_protocol_version": protocol_version,
            "freeze_errors_ignored": errors if args.allow_unfrozen else [],
            "model": args.model,
            "split": args.split,
            "instances": instance_ids,
            "ablations": args.ablations,
            "samples_per_instance": args.samples,
            "sample_seeds": sample_seeds,
            "max_workers": args.max_workers,
            "retrieval_configuration": retrieval_config,
            "expected_cells": [
                {
                    "model": args.model,
                    "method": spec["method"],
                    "split": args.split,
                    "instance": instance_id,
                    "sample_index": sample_index,
                    "ablation": ablation_id,
                }
                for instance_id in instance_ids
                for sample_index in range(args.samples)
                for ablation_id, spec, _ in conditions
            ],
            "runs": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_json(summary_path, summary)

    completed_cells = {
        (item["instance"], item["sample_index"], item["ablation"])
        for item in summary.get("runs", [])
        if item.get("status") == "recorded"
    }
    retrieval_session: dict | None = None
    if embedder is not None:
        retrieval_session = {"session_id": uuid.uuid4().hex, **embedder.usage()}
        summary.setdefault("retrieval_usage_sessions", []).append(retrieval_session)
        _write_json(summary_path, summary)

    pending: list[tuple[Path, Path, int, str, dict, int, dict]] = []
    for workspace, instance in selected:
        for sample_index in range(args.samples):
            for ablation_id, spec, repair_budget in conditions:
                cell = (workspace.name, sample_index, ablation_id)
                if cell in completed_cells:
                    continue
                view = dict(spec.get("view", {}))
                view["id"] = ablation_id
                if spec.get("oracle_candidates"):
                    view["candidate_document"] = _oracle_candidates(instance, workspace)
                if spec.get("retrieval_strategy"):
                    view["candidate_document"] = retrieve_candidate_document(
                        workspace,
                        strategy=spec["retrieval_strategy"],
                        top_k=int(retrieval_config.get("top_k", 5)),
                        embedder=embedder,
                        reciprocal_rank_constant=int(
                            retrieval_config.get("hybrid_reciprocal_rank_constant", 60)
                        ),
                    )
                    if embedder is not None and retrieval_session is not None:
                        retrieval_session.update(embedder.usage())
                pending.append(
                    (workspace, instance, sample_index, ablation_id, spec, repair_budget, view)
                )
    if retrieval_session is not None:
        _write_json(summary_path, summary)

    def execute_cell(task: tuple[Path, Path, int, str, dict, int, dict]):
        workspace, instance, sample_index, ablation_id, spec, repair_budget, view = task
        sample_model = replace(roster[args.model], seed=sample_seeds[sample_index])
        manifest = run_one(
            spec["method"],
            workspace=workspace,
            instance_dir=instance,
            model=sample_model,
            runs_root=args.runs_root,
            repair_budget=repair_budget,
            repair_with_execution=spec.get("repair_with_execution"),
            batch_id=batch_id,
            sample_index=sample_index,
            freeze_document=freeze,
            roster_path=args.config,
            freeze_path=args.freeze_config,
            ablation=view,
        )
        return task, manifest

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [executor.submit(execute_cell, task) for task in pending]
        for future in as_completed(futures):
            task, manifest = future.result()
            workspace, _, sample_index, ablation_id, spec, _, _ = task
            run_dir = args.runs_root / manifest["run_id"]
            manifest_path = run_dir / "manifest.json"
            if manifest.get("method_status") == "llm_error":
                summary.setdefault("invalid_attempts", []).append(
                    {
                        "model": args.model,
                        "method": spec["method"],
                        "split": args.split,
                        "instance": workspace.name,
                        "sample_index": sample_index,
                        "ablation": ablation_id,
                        "run_id": manifest["run_id"],
                        "manifest_path": str(manifest_path.resolve()),
                        "message": manifest.get("method_error"),
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                _write_json(summary_path, summary)
                print(
                    f"recorded invalid infrastructure attempt {ablation_id} "
                    f"{workspace.name} sample={sample_index}; cell remains pending"
                )
                continue
            summary["runs"].append(
                {
                    "status": "recorded",
                    "model": args.model,
                    "method": spec["method"],
                    "split": args.split,
                    "instance": workspace.name,
                    "sample_index": sample_index,
                    "seed": sample_seeds[sample_index],
                    "ablation": ablation_id,
                    "run_id": manifest["run_id"],
                    "manifest_path": str(manifest_path.resolve()),
                }
            )
            completed_cells.add((workspace.name, sample_index, ablation_id))
            _write_json(summary_path, summary)
            print(f"recorded {ablation_id} {workspace.name} sample={sample_index}")

    summary["expected_cell_count"] = len(selected) * args.samples * len(conditions)
    summary["recorded_cell_count"] = len(completed_cells)
    if summary["recorded_cell_count"] != summary["expected_cell_count"]:
        summary["status"] = "incomplete_infrastructure"
        _write_json(summary_path, summary)
        print(
            f"error: ablation batch has {summary['recorded_cell_count']}/"
            f"{summary['expected_cell_count']} unique cells",
            file=sys.stderr,
        )
        print(f"resume with --batch-summary {summary_path.resolve()}", file=sys.stderr)
        return 1
    summary["status"] = "complete"
    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(summary_path, summary)
    if args.split == "validation" and not args.allow_unfrozen:
        _write_json(
            validation_lock,
            {
                "freeze_id": freeze["freeze_id"],
                "batch_id": batch_id,
                "batch_summary": str(summary_path.resolve()),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    print(f"complete: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
