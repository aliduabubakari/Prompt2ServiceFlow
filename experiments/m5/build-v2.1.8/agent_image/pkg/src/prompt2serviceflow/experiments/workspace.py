"""Allowlist builder for isolated public submission workspaces.

Implements the generation-side of the experiment architecture in
``plan_experiement_evals.md`` Section 7: every method (M0-M5) runs inside a
per-instance workspace that contains only the public view of a benchmark
instance. Workspaces are built by *allowlist* -- only known-public files are
copied -- never by removing known-private files from a full copy.

Public view per instance workspace::

    <split>/<instance_id>/
      task.md                     # natural-language requirement (public input)
      candidates/candidate_sets.yaml
      contracts/                  # public artifact JSON schemas
      fixtures/                   # public sample inputs (expectation-free)
      catalog/                    # sanitized catalog snapshot at the authored pin
        catalog.yaml              #   generation block stripped
        services/*.yaml           #   provenance blocks stripped (source_refs leak)
      schemas/                    # public schemas (ServiceFlowIR, descriptor, runtime manifest)
      bin/                        # public tool contracts (validate_submission, compile)
      submission/                 # the only location a method may write
      workspace.yaml              # integrity manifest (inventory + sha256)

The builder is evaluation-side tooling: it may read private benchmark files
(e.g. ``gold/serviceflow.yaml``) solely to determine the authored catalog pin
and to verify integrity. Nothing private is copied into a workspace.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

BUILDER_NAME = "build_submission_workspace"
BUILDER_VERSION = "1.1.0"
WORKSPACE_MANIFEST_VERSION = "1.0.0"

CORE_SPLITS = ("main", "validation")
CORPUS_SPLITS = (*CORE_SPLITS, "extension")
SPLITS = CORE_SPLITS

PUBLIC_SCHEMA_FILES = (
    "serviceflow_ir.schema.json",
    "service_descriptor.schema.json",
    "runtime_manifest.schema.json",
)

# The workspace copies of the public schemas are sanitized as well: the
# descriptor schema must not document the stripped ``provenance`` block, and
# the IR schema must not document the private ``internal_spec_*`` fields.
DESCRIPTOR_SCHEMA_STRIP_PROPERTIES = ("provenance",)
IR_SCHEMA_SOURCE_STRIP_PROPERTIES = ("internal_spec_path", "internal_spec_sha256")
# Evidence-source enum values that encode benchmark authoring provenance.
# Submissions may only legitimately cite the public description.
IR_SCHEMA_STRIP_ENUM_VALUES = frozenset({"internal_spec", "reviewer_inference"})

# Keys that would turn the public candidate file into an oracle. The candidate
# file is verified label-free before it is copied.
CANDIDATE_FORBIDDEN_KEYS = frozenset({"labels", "required_service_id"})

# Fixture manifests occasionally embed semantic expectations (e.g.
# ``expected_route``). Any JSON/YAML fixture file containing such keys is
# excluded from the public view and logged as an exclusion.
EXPECTATION_KEY_PREFIXES = ("expected", "assert")

# Catalog sanitization. Descriptor ``provenance.source_refs`` enumerate the
# exact instance and source steps a service was authored from, which is a
# direct gold-binding oracle. ``catalog.yaml``'s ``generation`` block is
# authoring metadata. Both are stripped from the public catalog view.
DESCRIPTOR_STRIP_KEYS = ("provenance",)
CATALOG_INDEX_STRIP_KEYS = ("generation",)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BENCHMARK_ROOT = REPO_ROOT / "benchmark"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "experiments" / "workspaces"
TOOLS_BIN_DIR = REPO_ROOT / "experiments" / "tools" / "bin"
SCHEMAS_DIR = REPO_ROOT / "schemas"


class WorkspaceBuildError(RuntimeError):
    """Raised when a workspace cannot be built safely."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _dump_yaml(document: Any) -> str:
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)


def _iter_mapping_keys(node: Any) -> Iterable[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key)
            yield from _iter_mapping_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_mapping_keys(item)


def _expectation_keys(node: Any, path: str = "") -> list[str]:
    """Return dotted paths of keys that look like semantic expectations."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            key_text = str(key)
            dotted = f"{path}.{key_text}" if path else key_text
            if key_text.lower().startswith(EXPECTATION_KEY_PREFIXES):
                found.append(dotted)
            found.extend(_expectation_keys(value, dotted))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(_expectation_keys(item, f"{path}[{index}]"))
    return found


def _read_source_metadata(instance_dir: Path) -> dict[str, Any]:
    metadata_path = instance_dir / "source" / "source_metadata.yaml"
    if not metadata_path.is_file():
        raise WorkspaceBuildError(f"missing source metadata: {metadata_path}")
    return _load_yaml(metadata_path)


def _resolve_description(instance_dir: Path) -> tuple[Path, str]:
    """Locate the public requirement text and verify its recorded digest."""
    metadata = _read_source_metadata(instance_dir)
    description = metadata.get("description") or {}
    relative = description.get("path")
    recorded = description.get("sha256")
    if not relative or not recorded:
        raise WorkspaceBuildError(f"description path/sha256 missing in {instance_dir}")
    description_path = (REPO_ROOT / relative).resolve()
    try:
        description_path.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise WorkspaceBuildError(f"description path escapes repository: {relative}") from exc
    if not description_path.is_file():
        raise WorkspaceBuildError(f"description file not found: {relative}")
    actual = _sha256_file(description_path)
    if actual != recorded:
        raise WorkspaceBuildError(
            f"description sha256 mismatch for {relative}: {actual} != {recorded}"
        )
    return description_path, actual


def _resolve_catalog_pin(instance_dir: Path, override: str | None) -> tuple[str, str]:
    """Return the authored catalog snapshot version and catalog.yaml sha256.

    Reads ``gold/serviceflow.yaml`` for the pin only; nothing else is taken
    from gold. This is the authoritative snapshot the instance was authored
    and validated against.
    """
    if override is not None:
        serviceflow = _load_yaml(instance_dir / "gold" / "serviceflow.yaml")
        return override, str(serviceflow["catalog_snapshot"]["sha256"])
    serviceflow_path = instance_dir / "gold" / "serviceflow.yaml"
    if not serviceflow_path.is_file():
        raise WorkspaceBuildError(f"missing gold serviceflow for catalog pin: {serviceflow_path}")
    serviceflow = _load_yaml(serviceflow_path)
    snapshot = serviceflow.get("catalog_snapshot") or {}
    version = snapshot.get("version")
    recorded = snapshot.get("sha256")
    if not version or not recorded:
        raise WorkspaceBuildError(f"catalog_snapshot pin missing in {serviceflow_path}")
    return str(version), str(recorded)


class _Inventory:
    """Tracks copied files with digests, relative to the workspace root."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.files: list[dict[str, Any]] = []

    def record(self, path: Path, data: bytes) -> None:
        self.files.append(
            {
                "path": path.relative_to(self.workspace_root).as_posix(),
                "sha256": _sha256_bytes(data),
                "bytes": len(data),
            }
        )

    def write(self, relative: str, data: bytes) -> None:
        destination = self.workspace_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        self.record(destination, data)

    def copy_file(self, source: Path, relative: str) -> None:
        self.write(relative, source.read_bytes())


def _sanitize_descriptor(text: str) -> tuple[str, list[str]]:
    document = yaml.safe_load(text)
    removed = [key for key in DESCRIPTOR_STRIP_KEYS if isinstance(document, dict) and key in document]
    for key in removed:
        document.pop(key, None)
    return _dump_yaml(document), removed


def _sanitize_catalog_index(text: str) -> tuple[str, list[str]]:
    document = yaml.safe_load(text)
    removed = [key for key in CATALOG_INDEX_STRIP_KEYS if isinstance(document, dict) and key in document]
    for key in removed:
        document.pop(key, None)
    return _dump_yaml(document), removed


def _sanitize_schema(name: str, text: str) -> tuple[str, list[str]]:
    document = json.loads(text)
    removed: list[str] = []
    properties = document.get("properties") or {}
    if name == "service_descriptor.schema.json":
        for key in DESCRIPTOR_SCHEMA_STRIP_PROPERTIES:
            if key in properties:
                properties.pop(key)
                removed.append(f"properties.{key}")
            required = document.get("required") or []
            if key in required:
                required.remove(key)
                removed.append(f"required:{key}")
    if name == "serviceflow_ir.schema.json":
        source = properties.get("source") or {}
        source_properties = source.get("properties") or {}
        source_required = source.get("required") or []
        for key in IR_SCHEMA_SOURCE_STRIP_PROPERTIES:
            if key in source_properties:
                source_properties.pop(key)
                removed.append(f"properties.source.properties.{key}")
            if key in source_required:
                source_required.remove(key)
                removed.append(f"properties.source.required:{key}")
        removed.extend(_strip_enum_values(document))
    return json.dumps(document, indent=2) + "\n", removed


def _strip_enum_values(node: Any, path: str = "") -> list[str]:
    removed: list[str] = []
    if isinstance(node, dict):
        enum = node.get("enum")
        if isinstance(enum, list) and any(value in IR_SCHEMA_STRIP_ENUM_VALUES for value in enum):
            kept = [value for value in enum if value not in IR_SCHEMA_STRIP_ENUM_VALUES]
            dropped = sorted(set(enum) - set(kept))
            node["enum"] = kept
            removed.append(f"enum{path}:-{','.join(dropped)}")
        for key, value in node.items():
            removed.extend(_strip_enum_values(value, f"{path}/{key}"))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            removed.extend(_strip_enum_values(item, f"{path}[{index}]"))
    return removed


def _verify_candidate_document(document: Any, source: Path) -> None:
    forbidden = sorted(set(_iter_mapping_keys(document)) & CANDIDATE_FORBIDDEN_KEYS)
    if forbidden:
        raise WorkspaceBuildError(
            f"candidate file {source} contains label keys {forbidden}; refusing to copy"
        )


def _fixture_exclusion_reason(path: Path) -> tuple[str | None, list[str]]:
    """Return (reason, matched keys) if a fixture file embeds expectations."""
    if path.suffix.lower() not in {".json", ".yaml", ".yml"}:
        return None, []
    try:
        document = _load_yaml(path)
    except yaml.YAMLError:
        return None, []
    matched = _expectation_keys(document)
    if matched:
        return "expectation_keys_present", sorted(matched)
    return None, []


def build_workspace(
    instance_dir: Path,
    output_root: Path,
    *,
    split: str,
    benchmark_root: Path = DEFAULT_BENCHMARK_ROOT,
    catalog_version_override: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Build one instance workspace and return its manifest."""
    instance_dir = instance_dir.resolve()
    instance_id = instance_dir.name
    workspace_dir = output_root / split / instance_id
    if workspace_dir.exists():
        if not force:
            raise WorkspaceBuildError(
                f"workspace already exists (use force to rebuild): {workspace_dir}"
            )
        shutil.rmtree(workspace_dir)
    workspace_dir.mkdir(parents=True)

    transforms: list[str] = []
    detailed_transforms: list[str] = []
    exclusions: list[dict[str, Any]] = []
    inventory = _Inventory(workspace_dir)

    # task.md: the public natural-language requirement.
    description_path, description_sha = _resolve_description(instance_dir)
    inventory.copy_file(description_path, "task.md")

    # candidates/candidate_sets.yaml: verified label-free; the catalog pin is
    # normalized to the workspace catalog so model-visible files agree.
    candidate_source = instance_dir / "candidates" / "candidate_sets.yaml"
    if not candidate_source.is_file():
        raise WorkspaceBuildError(f"missing candidate sets: {candidate_source}")
    candidate_document = _load_yaml(candidate_source)
    _verify_candidate_document(candidate_document, candidate_source)
    catalog_version, catalog_index_sha = _resolve_catalog_pin(
        instance_dir, catalog_version_override
    )
    snapshot_block = candidate_document.get("catalog_snapshot") or {}
    if snapshot_block.get("version") != catalog_version:
        candidate_document["catalog_snapshot"] = {
            "catalog_id": snapshot_block.get("catalog_id", "serviceflow_catalog"),
            "version": catalog_version,
        }
        transforms.append("candidate_catalog_pin_normalized")
    inventory.write(
        "candidates/candidate_sets.yaml", _dump_yaml(candidate_document).encode("utf-8")
    )

    # contracts/: public artifact interface schemas, copied verbatim.
    contracts_dir = instance_dir / "contracts"
    if contracts_dir.is_dir():
        for source in sorted(contracts_dir.rglob("*")):
            if source.is_file():
                inventory.copy_file(source, f"contracts/{source.relative_to(contracts_dir).as_posix()}")

    # fixtures/: public sample inputs; manifests embedding semantic
    # expectations are excluded and logged.
    fixtures_dir = instance_dir / "fixtures"
    if fixtures_dir.is_dir():
        for source in sorted(fixtures_dir.rglob("*")):
            if not source.is_file():
                continue
            relative = f"fixtures/{source.relative_to(fixtures_dir).as_posix()}"
            reason, matched = _fixture_exclusion_reason(source)
            if reason is not None:
                exclusions.append({"path": relative, "reason": reason, "matched_keys": matched})
                continue
            inventory.copy_file(source, relative)

    # catalog/: sanitized snapshot at the authored pin. The raw snapshot
    # catalog.yaml digest must match the pin recorded in gold serviceflow.
    snapshot_dir = benchmark_root / "catalog" / "snapshots" / catalog_version
    catalog_index_path = snapshot_dir / "catalog.yaml"
    if not catalog_index_path.is_file():
        raise WorkspaceBuildError(f"catalog snapshot not found: {snapshot_dir}")
    actual_index_sha = _sha256_file(catalog_index_path)
    if catalog_version_override is None and actual_index_sha != catalog_index_sha:
        raise WorkspaceBuildError(
            f"catalog.yaml sha256 mismatch for snapshot {catalog_version}: "
            f"{actual_index_sha} != pinned {catalog_index_sha}"
        )
    sanitized_index, removed_index_keys = _sanitize_catalog_index(catalog_index_path.read_text())
    inventory.write("catalog/catalog.yaml", sanitized_index.encode("utf-8"))
    if removed_index_keys:
        transforms.append("catalog_index_stripped")
        detailed_transforms.append(f"catalog_index_stripped:{','.join(removed_index_keys)}")
    descriptor_count = 0
    stripped_count = 0
    for source in sorted((snapshot_dir / "services").glob("*.yaml")):
        sanitized, removed = _sanitize_descriptor(source.read_text())
        descriptor_count += 1
        stripped_count += int(bool(removed))
        inventory.write(f"catalog/services/{source.name}", sanitized.encode("utf-8"))
    transforms.append(f"descriptor_provenance_stripped:{stripped_count}/{descriptor_count}")
    detailed_transforms.append(transforms[-1])

    # schemas/: public schemas only (never examples, which mirror gold).
    # Sanitized so they do not document stripped descriptor provenance or the
    # private internal-spec fields.
    for name in PUBLIC_SCHEMA_FILES:
        source = SCHEMAS_DIR / name
        if not source.is_file():
            raise WorkspaceBuildError(f"missing public schema: {source}")
        sanitized_schema, removed_schema_keys = _sanitize_schema(name, source.read_text())
        inventory.write(f"schemas/{name}", sanitized_schema.encode("utf-8"))
        if removed_schema_keys:
            # workspace.yaml records the coarse transform only; field-level
            # detail (which would itself contain private vocabulary) goes to
            # the evaluation-side build manifest.
            transforms.append(f"schema_stripped:{name}")
            detailed_transforms.append(f"schema_stripped:{name}:{','.join(removed_schema_keys)}")

    # bin/: public tool contracts and wrappers (validate_submission, compile).
    # Executable wrappers keep their execute bit inside the workspace.
    if TOOLS_BIN_DIR.is_dir():
        for source in sorted(TOOLS_BIN_DIR.iterdir()):
            if source.is_file():
                inventory.copy_file(source, f"bin/{source.name}")
                destination = workspace_dir / "bin" / source.name
                if source.read_bytes().startswith(b"#!"):
                    destination.chmod(0o755)

    # submission/: the only writable location for methods.
    (workspace_dir / "submission").mkdir(exist_ok=True)

    metadata = _read_source_metadata(instance_dir)
    sanitized_index_entry = next(
        item for item in inventory.files if item["path"] == "catalog/catalog.yaml"
    )
    manifest: dict[str, Any] = {
        "workspace_manifest_version": WORKSPACE_MANIFEST_VERSION,
        "builder": {"name": BUILDER_NAME, "version": BUILDER_VERSION},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "instance": {
            "id": instance_id,
            "split": split,
            "benchmark_id": metadata.get("benchmark_id"),
        },
        "task": {"description_sha256": description_sha},
        "catalog": {
            "version": catalog_version,
            "pinned_catalog_yaml_sha256": catalog_index_sha,
            "sanitized_catalog_yaml_sha256": sanitized_index_entry["sha256"],
            "descriptor_count": descriptor_count,
        },
        "transforms": sorted(transforms),
        "exclusions": [{"path": item["path"], "reason": item["reason"]} for item in exclusions],
        "file_count": len(inventory.files),
        "files": sorted(inventory.files, key=lambda item: item["path"]),
    }
    manifest_bytes = (_dump_yaml(manifest)).encode("utf-8")
    (workspace_dir / "workspace.yaml").write_bytes(manifest_bytes)

    return {
        "instance_id": instance_id,
        "split": split,
        "workspace": str(workspace_dir),
        "catalog_version": catalog_version,
        "file_count": len(inventory.files),
        "exclusions": exclusions,
        "transforms": sorted(transforms),
        "detailed_transforms": sorted(detailed_transforms),
    }


def iter_instance_dirs(benchmark_root: Path, split: str) -> Iterable[Path]:
    split_dir = benchmark_root / "instances" / split
    if not split_dir.is_dir():
        raise WorkspaceBuildError(f"split directory not found: {split_dir}")
    for child in sorted(split_dir.iterdir()):
        if child.is_dir() and (child / "source" / "source_metadata.yaml").is_file():
            yield child


def build_workspaces(
    *,
    benchmark_root: Path = DEFAULT_BENCHMARK_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    splits: Iterable[str] = SPLITS,
    instance_ids: Iterable[str] | None = None,
    catalog_version_override: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Build workspaces for the selected instances and write a build manifest."""
    selected = set(instance_ids) if instance_ids else None
    results: list[dict[str, Any]] = []
    for split in splits:
        for instance_dir in iter_instance_dirs(benchmark_root, split):
            if selected is not None and instance_dir.name not in selected:
                continue
            results.append(
                build_workspace(
                    instance_dir,
                    output_root,
                    split=split,
                    benchmark_root=benchmark_root,
                    catalog_version_override=catalog_version_override,
                    force=force,
                )
            )
    if selected is not None:
        built = {result["instance_id"] for result in results}
        missing = sorted(selected - built)
        if missing:
            raise WorkspaceBuildError(f"requested instances not found: {missing}")

    output_root.mkdir(parents=True, exist_ok=True)
    build_manifest = {
        "builder": {"name": BUILDER_NAME, "version": BUILDER_VERSION},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_root": str(benchmark_root),
        "output_root": str(output_root),
        "catalog_version_override": catalog_version_override,
        "workspace_count": len(results),
        "workspaces": results,
    }
    manifest_path = output_root / "_build_manifest.json"
    manifest_path.write_text(json.dumps(build_manifest, indent=2) + "\n", encoding="utf-8")
    return build_manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--split",
        choices=["main", "validation", "extension", "all", "corpus"],
        default="all",
        help="which benchmark split to build (default: all)",
    )
    parser.add_argument(
        "--instances",
        nargs="*",
        default=None,
        help="optional explicit instance ids to build",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help=f"workspace output root (default: {DEFAULT_OUTPUT_ROOT})",
    )
    parser.add_argument(
        "--benchmark-root",
        type=Path,
        default=DEFAULT_BENCHMARK_ROOT,
        help="benchmark root containing instances/ and catalog/",
    )
    parser.add_argument(
        "--catalog-version",
        default=None,
        help="override the authored catalog pin for every workspace (not recommended)",
    )
    parser.add_argument("--force", action="store_true", help="rebuild existing workspaces")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list the instances that would be built without writing anything",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    splits = (
        CORPUS_SPLITS
        if args.split == "corpus"
        else CORE_SPLITS
        if args.split == "all"
        else (args.split,)
    )
    if args.dry_run:
        for split in splits:
            for instance_dir in iter_instance_dirs(args.benchmark_root, split):
                if args.instances and instance_dir.name not in args.instances:
                    continue
                print(f"would build {split}/{instance_dir.name}")
        return 0
    try:
        manifest = build_workspaces(
            benchmark_root=args.benchmark_root,
            output_root=args.output,
            splits=splits,
            instance_ids=args.instances,
            catalog_version_override=args.catalog_version,
            force=args.force,
        )
    except WorkspaceBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    total_exclusions = sum(len(item["exclusions"]) for item in manifest["workspaces"])
    print(
        f"built {manifest['workspace_count']} workspaces under {manifest['output_root']} "
        f"({total_exclusions} fixture exclusions)"
    )
    for item in manifest["workspaces"]:
        print(
            f"  {item['split']}/{item['instance_id']}: catalog {item['catalog_version']}, "
            f"{item['file_count']} files, {len(item['exclusions'])} exclusions"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
