#!/usr/bin/env python3
"""Verify relocated, sealed profile-38.1 evidence and reproduce Table 6.

This reader never executes archived code. Original paths and bytes stay sealed;
the separate content-addressed map provides relocation, including absent pins.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath

from prepare_evaluation_final_results import bca_mean


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    a = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    store = a.evidence_root.resolve()
    manifest = json.loads((store / "MANIFEST.json").read_text())
    pin = json.loads((root / "replication/POSTHOC_MANIFEST.json").read_text())
    files = manifest["files"]
    if fingerprint(files) != manifest["file_map_fingerprint"] or manifest["file_map_fingerprint"] != pin["file_map_fingerprint"]:
        raise ValueError("Frozen evidence map changed")
    verified = set()

    def logical(name):
        p = PurePosixPath(name)
        if not p.is_absolute():
            return "semantic/" + p.as_posix()
        for label, historical in manifest["historical_roots"].items():
            old = PurePosixPath(historical)
            if p.is_relative_to(old):
                return label + "/" + p.relative_to(old).as_posix()
        raise ValueError("Unmapped historical path")

    def read(name, verify_only=False):
        key = name if name.startswith(("semantic/", "original/")) else logical(name)
        digest = files[key]
        if digest == "MISSING":
            raise ValueError("Cannot read an intentionally absent input: " + key)
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError("Invalid content address")
        if verify_only and digest in verified:
            return b""
        data = (store / "blobs" / digest).read_bytes()
        if digest not in verified:
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError("Changed evidence object: " + digest)
            verified.add(digest)
        return data

    def document(name):
        return json.loads(read(name))

    prefix = "semantic/audit/evaluator_only/" + manifest["package"] + "/"
    run = document(prefix + "run.json")
    seal = document(prefix + "output_sha256.json")
    inputs = document(prefix + "input_sha256.json")
    if run["status"] != "complete" or not run["source_inputs_unchanged"] or run["llm_calls"] != 0:
        raise ValueError("Replay is not complete and immutable")
    if fingerprint(inputs) != run["input_fingerprint"] or fingerprint(seal["files"]) != seal["output_fingerprint"]:
        raise ValueError("Original input/output fingerprint changed")
    if seal["output_fingerprint"] != pin["sealed_output_fingerprint"]:
        raise ValueError("Wrong post-hoc experiment")
    # Verify all original pins, retaining recorded absences, and all output bytes.
    for name, expected in inputs.items():
        if files.get(logical(name)) != expected:
            raise ValueError("Original input mapping changed: " + name)
        if expected != "MISSING":
            read(name, verify_only=True)
    actual = {name[len(prefix):] for name in files if name.startswith(prefix)}
    if actual != set(seal["files"]) | {seal["self_excluded"]}:
        raise ValueError("Sealed output roster changed")
    for name, expected in seal["files"].items():
        if files[prefix + name] != expected:
            raise ValueError("Output mapping changed")
        read(prefix + name, verify_only=True)
    plan, references = document(prefix + "plan.json"), document(prefix + "reference_plan.json")
    # csv_postgres_ops.canonical_bytes is the historical plan canonicalization;
    # it differs from the input/output inventory fingerprint by a trailing newline.
    plan_bytes = (json.dumps({"models": plan, "references": references}, ensure_ascii=False, sort_keys=True) + "\n").encode()
    if hashlib.sha256(plan_bytes).hexdigest() != run["plan_fingerprint"]:
        raise ValueError("Frozen model/reference plans changed")
    if len(plan) != 2970 or len(references) != 110:
        raise ValueError("Incomplete frozen cohort")
    if set(run["completed_cells"]) != {row["source"]["id"] for row in plan}:
        raise ValueError("Foreign or missing model checkpoint")
    if set(run["reference_controls"]) != {row["source"]["id"] for row in references}:
        raise ValueError("Foreign or missing reference checkpoint")

    cell_directories = {str(PurePosixPath(logical(entry["path"])).parent) + "/"
                        for entry in (*run["completed_cells"].values(), *run["reference_controls"].values())}
    cell_files = {directory: {} for directory in cell_directories}
    for name, digest in files.items():
        if "/attempt_" not in name:
            continue
        before, after = name.split("/attempt_", 1)
        if "/" not in after:
            continue
        attempt, relative = after.split("/", 1)
        directory = before + "/attempt_" + attempt + "/"
        if directory in cell_files and relative != "result.json":
            cell_files[directory][relative] = digest

    def checkpoint(entry, identity):
        key = logical(entry["path"])
        if files[key] != entry["sha256"]:
            raise ValueError("Checkpoint digest changed")
        result = document(key)
        if result["source"] != identity:
            raise ValueError("Checkpoint source identity changed")
        directory = str(PurePosixPath(key).parent) + "/"
        expected = result["evidence_files"]
        actual = cell_files[directory]
        if actual != expected:
            raise ValueError("Checkpoint evidence inventory changed")
        return result

    reference_rows = []
    for row in references:
        source = row["source"]
        result = checkpoint(run["reference_controls"][source["id"]], source)
        if not result["profile_conformance"]["pass"]:
            raise ValueError("Reference profile control failed")
        reference_rows.append({"case": source["case"], "profile_conformance": True,
                               "full_assertion_pass": result["role_matched_assertion_pass"]})
    if sum(r["full_assertion_pass"] for r in reference_rows) != 73:
        raise ValueError("Reference assertion outcomes changed")

    with (root / "results/paper/analysis/primary_run_level.csv").open(newline="") as handle:
        original = {(r["model"], r["method"], r["split"] + "/" + r["instance"], int(r["sample_index"])): r
                    for r in csv.DictReader(handle) if r["method"] in {"m3", "m4", "m5"}}
    rows = []
    for planned in plan:
        source = planned["source"]
        result = checkpoint(run["completed_cells"][source["id"]], source)
        key = (source["model"], source["method"], source["case"], source["sample_index"])
        original_row = original[key]
        public = bool(float(original_row["executable_valid"]))
        if public != source["published_executable_valid"]:
            raise ValueError("Original public-valid outcome changed")
        original_pass = bool(float(original_row["semantic_success"]))
        if original_pass != source["published_semantic_success"]:
            raise ValueError("Original assertion outcome changed")
        passed = result.get("role_matched_assertion_pass") is True
        if passed and (not public or result["state"] != "replayed" or not result["profile_conformance"]["pass"]):
            raise ValueError("Unsupported or invalid observation counted as a pass")
        if result["state"] == "replayed":
            ir = str(PurePosixPath(logical(run["completed_cells"][source["id"]]["path"])).parent / "compiled_submission/serviceflow.yaml")
            if files[ir] != planned["compilation"]["source_ir_sha256"]:
                raise ValueError("Saved IR bytes changed")
        observations = source["assertion_observations"]["assertion_message_counts"]
        rows.append({"id": source["id"], "model": source["model"], "method": source["method"],
                     "case": source["case"], "sample_index": source["sample_index"],
                     "original_public_valid": public, "original_assertion_pass": original_pass,
                     "original_missing_output": bool(observations.get("missing_or_empty_output_message")),
                     "original_failure_messages": json.dumps(observations, sort_keys=True),
                     "state": result["state"], "output_assertion_pass": passed,
                     "literal_path_assertion_pass": result.get("reviewed_assertion_pass") is True})
    states = Counter(row["state"] for row in rows)
    if states != Counter({"replayed": 781, "blocked_execution_profile": 16,
                          "not_replayed_original_public_invalid": 1432, "missing_saved_ir": 741}):
        raise ValueError("Execution-state reconciliation changed")
    groups = defaultdict(list)
    for row in rows:
        groups[row["model"], row["method"]].append(row)
    expected = json.loads((root / "replication/expected_results.json").read_text())
    targets = expected["table6_output_assertion_percent"]
    with (root / "results/paper/analysis/primary_summary.csv").open(newline="") as handle:
        public_summary = {(r["model"], r["method"]): r for r in csv.DictReader(handle)}
    labels = {"deepinfra-deepseek-v4-1-flash": "DeepSeek-Flash", "deepinfra-qwen3-coder-480b-turbo": "Qwen-480B", "sintef-qwen3-8-27b-nvfp4": "Qwen-27B"}
    summary, paired = [], []
    for (model, method), items in sorted(groups.items()):
        instances = defaultdict(list)
        for row in items:
            instances[row["case"]].append(row)
        if len(items) != 330 or len(instances) != 110 or any(sorted(x["sample_index"] for x in rs) != [0, 1, 2] for rs in instances.values()):
            raise ValueError("Incomplete model-method repetitions")
        values = [sum(r["output_assertion_pass"] for r in rs) / 3 for _, rs in sorted(instances.items())]
        low, high = bca_mean(values, f"execution_evidence_audit_639e71d3/{model}/{method}/role_pass")
        rate = 100 * sum(values) / len(values)
        if round(rate, 1) != targets[labels[model]][method]:
            raise ValueError("Final-PDF assertion rate mismatch")
        original_count = sum(r["original_assertion_pass"] for r in items)
        target = expected["table6_original_assertion_passes"][labels[model]][method]
        if original_count != target:
            raise ValueError("Original assertion count mismatch")
        public_stats = public_summary[model, method]
        public_rate = 100 * sum(r["original_public_valid"] for r in items) / 330
        if abs(public_rate / 100 - float(public_stats["executable_valid"])) > 1e-10:
            raise ValueError("Original public validity aggregate mismatch")
        summary.append({"model": labels[model], "method": method.upper(), "declared": 330,
                        "original_public_percent": public_rate,
                        "original_public_ci_low": 100 * float(public_stats["executable_valid_ci_low"]),
                        "original_public_ci_high": 100 * float(public_stats["executable_valid_ci_high"]),
                        "original_assertion_passes": original_count,
                        "original_assertion_percent": 100 * original_count / 330,
                        "posthoc_assertion_passes": sum(r["output_assertion_pass"] for r in items),
                        "output_assertion_percent": rate, "ci_low": 100 * low, "ci_high": 100 * high})
        eligible_failures = [r for r in items if r["original_public_valid"] and not r["original_assertion_pass"]]
        gained = [r for r in eligible_failures if r["output_assertion_pass"]]
        lost = sum(r["original_assertion_pass"] and not r["output_assertion_pass"] for r in items)
        paired.append({"model": labels[model], "method": method.upper(), "declared": 330,
                       "original_pass_to_pass": original_count - lost, "fail_to_pass": len(gained),
                       "pass_to_fail": lost, "fail_to_fail": 330 - original_count - len(gained),
                       "original_public_valid_assertion_failures": len(eligible_failures),
                       "original_missing_output_among_public_valid_failures": sum(r["original_missing_output"] for r in eligible_failures),
                       "gains_with_original_missing_output": sum(r["original_missing_output"] for r in gained),
                       "revised_runtime_literal_path_passes": sum(r["literal_path_assertion_pass"] for r in items)})
        if method == "m4":
            fields = expected["m4_paired_assertion_targets"][labels[model]]
            if any(paired[-1][key] != value for key, value in fields.items()):
                raise ValueError("M4 paired assertion target mismatch")
    a.out.mkdir(parents=True, exist_ok=True)
    for name, records in (("table6.csv", summary), ("run_level.csv", rows),
                          ("reference_controls.csv", reference_rows), ("paired_assertions.csv", paired)):
        with (a.out / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    tex = [r"\begin{tabular}{@{}llrrr@{}}", r"\toprule",
           r"Model & Method & \shortstack{Exec. validity\\(original)} & "
           r"\shortstack{G6-Assert\\(original)} & \shortstack{G6-Assert\\(post-hoc)} \\", r"\midrule"]
    for r in summary:
        tex.append(f"{r['model']} & {r['method']} & {r['original_public_percent']:.1f} "
                   f"({r['original_public_ci_low']:.1f}--{r['original_public_ci_high']:.1f}) & "
                   f"{r['original_assertion_percent']:.1f} ({r['original_assertion_passes']}) & "
                   f"{r['output_assertion_percent']:.1f} ({r['ci_low']:.1f}--{r['ci_high']:.1f}) " + r"\\")
    (a.out / "table6.tex").write_text("\n".join(tex + [r"\bottomrule", r"\end{tabular}"]) + "\n")
    report = {"status": "pass", "declared": len(rows), "eligible_original_public_valid": sum(r["original_public_valid"] for r in rows),
              "states": dict(states), "reference_controls": len(reference_rows), "reference_assertion_passes": 73,
              "input_pins_verified": len(inputs), "sealed_output_files_verified": len(seal["files"]),
              "unique_objects_verified": len(verified), "model_calls": 0, "runtime_executions": 0,
              "scope": "Saved-evidence verification and aggregation; no new runtime or inference",
              "source_output_fingerprint": seal["output_fingerprint"]}
    (a.out / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
