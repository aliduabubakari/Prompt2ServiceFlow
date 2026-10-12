"""Leakage scanner for public submission workspaces.

Implements the CI gate from ``plan_experiement_evals.md`` Sections 5 and 7:
before any experiment batch runs, every built workspace is walked and checked
for gold artifacts, private labels, assertion content, review records, and
authoring metadata. The scanner is fail-closed: any finding fails the batch.

Checks per workspace (relative to the instance workspace root):

1. Forbidden path components (``gold/``, ``runtime/``, ``argo/``, ...).
2. Forbidden file names (candidate labels, assertions, bindings, ...).
3. Forbidden content patterns (distractor-label vocabulary, provenance
   markers, expectation keys, internal-spec references).
4. Structural checks: candidate files carry no labels; fixture JSON/YAML
   carries no expectation keys; workspace catalog descriptors carry no
   ``provenance`` block; workspace ``catalog.yaml`` carries no ``generation``.
5. No symlinks (workspaces must be self-contained).
6. Manifest integrity: every file listed in ``workspace.yaml`` exists with a
   matching sha256, and no unlisted files exist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterator

import yaml

SCANNER_NAME = "check_workspace_leakage"
SCANNER_VERSION = "1.0.0"

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WORKSPACE_ROOT = REPO_ROOT / "experiments" / "workspaces"

WORKSPACE_MANIFEST = "workspace.yaml"
BUILD_MANIFEST = "_build_manifest.json"

# Directory/file name components that must never appear inside a workspace.
FORBIDDEN_PATH_PARTS = frozenset(
    {
        "gold",
        "runtime",
        "argo",
        "review",
        "reviews",
        "source",
        "__pycache__",
    }
)

# Filename patterns (matched against the file name, case-insensitive).
FORBIDDEN_FILE_NAME_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"candidate_labels",
        r"^bindings\.ya?ml$",
        r"artifact_mappings",
        r"assertions",
        r"dockerfile",
        r"source_metadata",
        r"internal_spec",
        r"hardening",
        r"validation_report",
    )
)

# Content patterns that indicate label, provenance, or expectation leakage.
# Matched case-insensitively against decoded text content.
FORBIDDEN_CONTENT_PATTERNS: dict[str, re.Pattern[str]] = {
    "candidate_label_key": re.compile(r"\brequired_service_id\b", re.IGNORECASE),
    "distractor_label_vocabulary": re.compile(
        r"\b(?:semantic|target|contract|format)_mismatch\b"
        r"|\bmissing_required_output\b"
        r"|\bgeneric_escape_hatch\b"
        r"\bpolicy_incompatible\b",
        re.IGNORECASE,
    ),
    "distractor_terminology": re.compile(r"\bdistractor\w*\b", re.IGNORECASE),
    "provenance_source_refs": re.compile(r"\bsource_refs\b", re.IGNORECASE),
    "provenance_review_status": re.compile(r"\breview_status\b", re.IGNORECASE),
    "internal_spec_reference": re.compile(r"\binternal_spec\b", re.IGNORECASE),
    "gold_path_reference": re.compile(r"\bgold/", re.IGNORECASE),
}

# NOTE: there is deliberately no free-text pattern for ``expected_*`` /
# ``assert_*`` tokens. Service descriptors legitimately expose interface
# parameters with such names (e.g. a sensor's ``expected_statuses``), and the
# requirement text may use the same vocabulary. Expectation leakage is caught
# structurally instead: fixture JSON/YAML must not contain expectation keys
# (see _check_fixture_structure).

# Extensions scanned for content. Binary-ish fixtures (pdf/png) are skipped.
TEXT_SCAN_SUFFIXES = {
    ".json",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
    ".csv",
    ".sql",
    ".conf",
    ".jsonl",
    ".geojson",
    ".toml",
    ".py",
    ".sh",
}
MAX_SCAN_BYTES = 5 * 1024 * 1024

CANDIDATE_LABEL_KEYS = frozenset({"labels", "required_service_id"})
EXPECTATION_KEY_PREFIXES = ("expected", "assert")


def _iter_keys(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key)
            yield from _iter_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_keys(item)


def _finding(workspace: Path, kind: str, path: Path | str, detail: str) -> dict[str, str]:
    return {
        "workspace": str(workspace),
        "kind": kind,
        "path": str(path),
        "detail": detail,
    }


def iter_instance_workspaces(workspace_root: Path) -> Iterator[Path]:
    """Yield instance workspace directories (``<root>/<split>/<id>``)."""
    if not workspace_root.is_dir():
        return
    for split_dir in sorted(workspace_root.iterdir()):
        if not split_dir.is_dir():
            continue
        for workspace in sorted(split_dir.iterdir()):
            if workspace.is_dir() and (workspace / WORKSPACE_MANIFEST).is_file():
                yield workspace


def _check_paths(workspace: Path) -> Iterator[dict[str, str]]:
    for path in sorted(workspace.rglob("*")):
        relative = path.relative_to(workspace)
        if path.is_symlink():
            yield _finding(workspace, "symlink", relative, "workspaces must not contain symlinks")
            continue
        parts = {part.lower() for part in relative.parts[:-1]} if path.is_file() else {
            part.lower() for part in relative.parts
        }
        forbidden_parts = parts & FORBIDDEN_PATH_PARTS
        if forbidden_parts:
            yield _finding(
                workspace, "forbidden_path", relative, f"forbidden components: {sorted(forbidden_parts)}"
            )
        if path.is_file():
            for pattern in FORBIDDEN_FILE_NAME_PATTERNS:
                if pattern.search(path.name):
                    yield _finding(
                        workspace, "forbidden_file_name", relative, f"matched {pattern.pattern!r}"
                    )


def _check_content(workspace: Path) -> Iterator[dict[str, str]]:
    for path in sorted(workspace.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix.lower() not in TEXT_SCAN_SUFFIXES:
            continue
        if path.stat().st_size > MAX_SCAN_BYTES:
            continue
        text = path.read_bytes().decode("utf-8", errors="replace")
        relative = path.relative_to(workspace)
        for name, pattern in FORBIDDEN_CONTENT_PATTERNS.items():
            match = pattern.search(text)
            if match:
                yield _finding(
                    workspace,
                    "forbidden_content",
                    relative,
                    f"{name}: matched {match.group(0)!r}",
                )


def _check_candidate_structure(workspace: Path) -> Iterator[dict[str, str]]:
    candidate_path = workspace / "candidates" / "candidate_sets.yaml"
    if not candidate_path.is_file():
        yield _finding(workspace, "missing_file", "candidates/candidate_sets.yaml", "required public input missing")
        return
    document = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))
    forbidden = sorted(set(_iter_keys(document)) & CANDIDATE_LABEL_KEYS)
    if forbidden:
        yield _finding(
            workspace,
            "candidate_labels",
            "candidates/candidate_sets.yaml",
            f"label keys present: {forbidden}",
        )


def _check_fixture_structure(workspace: Path) -> Iterator[dict[str, str]]:
    fixtures_dir = workspace / "fixtures"
    if not fixtures_dir.is_dir():
        return
    for path in sorted(fixtures_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".json", ".yaml", ".yml"}:
            continue
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        matched = sorted(
            key for key in _iter_keys(document) if key.lower().startswith(EXPECTATION_KEY_PREFIXES)
        )
        if matched:
            yield _finding(
                workspace,
                "fixture_expectations",
                path.relative_to(workspace),
                f"expectation-like keys present: {matched}",
            )


def _check_catalog_sanitization(workspace: Path) -> Iterator[dict[str, str]]:
    catalog_dir = workspace / "catalog"
    if not catalog_dir.is_dir():
        yield _finding(workspace, "missing_file", "catalog/", "workspace catalog missing")
        return
    index_path = catalog_dir / "catalog.yaml"
    if not index_path.is_file():
        yield _finding(workspace, "missing_file", "catalog/catalog.yaml", "catalog index missing")
    else:
        document = yaml.safe_load(index_path.read_text(encoding="utf-8"))
        if isinstance(document, dict) and "generation" in document:
            yield _finding(
                workspace, "catalog_unsanitized", "catalog/catalog.yaml", "generation block present"
            )
    services_dir = catalog_dir / "services"
    descriptors = sorted(services_dir.glob("*.yaml")) if services_dir.is_dir() else []
    if not descriptors:
        yield _finding(workspace, "missing_file", "catalog/services/", "no service descriptors")
    for descriptor_path in descriptors:
        document = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
        if isinstance(document, dict) and "provenance" in document:
            yield _finding(
                workspace,
                "catalog_unsanitized",
                descriptor_path.relative_to(workspace),
                "provenance block present (source_refs oracle)",
            )


def _check_manifest_integrity(workspace: Path) -> Iterator[dict[str, str]]:
    manifest_path = workspace / WORKSPACE_MANIFEST
    document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    listed = {entry["path"]: entry for entry in document.get("files", [])}
    for relative, entry in listed.items():
        path = workspace / relative
        if not path.is_file():
            yield _finding(workspace, "manifest_integrity", relative, "listed file missing on disk")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != entry["sha256"]:
            yield _finding(workspace, "manifest_integrity", relative, "sha256 mismatch vs manifest")
    for path in sorted(workspace.rglob("*")):
        if not path.is_file() or path.name == WORKSPACE_MANIFEST:
            continue
        relative = path.relative_to(workspace).as_posix()
        if relative not in listed:
            yield _finding(workspace, "manifest_integrity", relative, "unlisted file present")


def scan_workspace(workspace: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    findings.extend(_check_paths(workspace))
    findings.extend(_check_content(workspace))
    findings.extend(_check_candidate_structure(workspace))
    findings.extend(_check_fixture_structure(workspace))
    findings.extend(_check_catalog_sanitization(workspace))
    findings.extend(_check_manifest_integrity(workspace))
    return findings


def scan_workspace_root(workspace_root: Path) -> dict[str, Any]:
    workspaces = list(iter_instance_workspaces(workspace_root))
    findings: list[dict[str, str]] = []
    for workspace in workspaces:
        findings.extend(scan_workspace(workspace))
    return {
        "scanner": {"name": SCANNER_NAME, "version": SCANNER_VERSION},
        "workspace_root": str(workspace_root),
        "workspaces_scanned": len(workspaces),
        "finding_count": len(findings),
        "findings": findings,
        "status": "pass" if not findings else "fail",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=DEFAULT_WORKSPACE_ROOT,
        help=f"root containing built workspaces (default: {DEFAULT_WORKSPACE_ROOT})",
    )
    parser.add_argument("--json", action="store_true", help="emit the full report as JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = scan_workspace_root(args.workspace_root)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"scanned {report['workspaces_scanned']} workspaces under {report['workspace_root']}: "
            f"{report['finding_count']} findings -> {report['status'].upper()}"
        )
        for finding in report["findings"]:
            print(f"  [{finding['kind']}] {finding['workspace']}: {finding['path']} -- {finding['detail']}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
