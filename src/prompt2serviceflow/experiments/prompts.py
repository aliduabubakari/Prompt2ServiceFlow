"""Visible-input builders and prompt templates for methods M0-M4.

Visibility is enforced *by construction*: these builders read only files
inside the submission workspace (which itself is allowlist-built and
leakage-scanned). A method physically cannot see what the builders do not
read, so the visible-input policy ``X_{j,m}`` of plan Section 5 is declared
by the code below and recorded in every run manifest.

Per-method visible views (experiments/README.md matrix):

- M0: task only.
- M1: task only (plus the DAG schema in instructions).
- M2: task + candidate sets + catalog payload + fixture previews.
- M3/M4: task + candidate sets + catalog payload + schemas + fixture
  previews (+ validator diagnostics for M4 repair).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# 1.0.0 initial; 1.1.0 smoke hardening: conformance-pitfalls block
# (idempotency/vocabulary-transfer), contracts/ added to M2-M4 visible
# views, runtime/scripts path fix. 1.2.0 enforces true M2/M3 contract-input
# parity by rendering the public artifact contracts in the M2 prompt. 1.3.0
# makes the authorized offline/mock setting explicit and hardens M5 against
# premature completion without artifacts or validation. 1.4.0 adds
# model-agnostic YAML/schema fidelity rules, fence-free multi-file output,
# deterministic-runtime constraints, and full public-schema context during
# M4 repair. 2.0.0 makes runtime packaging a deterministic IR projection:
# M3/M4 author only ServiceFlowIR, and M4 repairs only that source document.
# 2.0.1 adds M5-only public-schema/source-identity guidance and a bounded
# agent context after the first v6 Main smoke exposed context retransmission.
# 2.0.2 makes M4 gate-aware (G0 repairs no longer repeat the catalog and
# contracts) and calls out four observed schema-only Main-smoke failures.
# 2.0.3 serializes M3/M4 ServiceFlowIR responses as JSON, a strict YAML 1.2
# subset, so string values containing colons cannot be retyped as mappings.
# 2.1.0 adds bounded cumulative public-diagnostic history to M4 repairs and
# instructs the model not to reintroduce violations resolved in later states.
# Validation-20 remains untouched.
PROMPT_VERSION = "2.1.0"
# Versioned separately because these controls affect only registered ablation
# views and must not invalidate already-running frozen primary batches.
ABLATION_PROTOCOL_VERSION = "1.1.0"

FIXTURE_PREVIEW_MAX_BYTES = 2048
FIXTURE_PREVIEW_MAX_FILES = 6

# Method-visible file sets (the declared visible-input policy).
VISIBLE_VIEWS: dict[str, tuple[str, ...]] = {
    "m0": ("task.md",),
    "m1": ("task.md",),
    "m2": ("task.md", "candidates/", "catalog/", "contracts/", "fixtures/"),
    "m3": ("task.md", "candidates/", "catalog/", "contracts/", "schemas/", "fixtures/"),
    "m4": ("task.md", "candidates/", "catalog/", "contracts/", "schemas/", "fixtures/"),
}


def _read(workspace: Path, relative: str) -> str:
    return (workspace / relative).read_text(encoding="utf-8")


def load_task(workspace: Path) -> str:
    return _read(workspace, "task.md")


def load_candidates(workspace: Path) -> str:
    return _read(workspace, "candidates/candidate_sets.yaml")


def load_workspace_manifest(workspace: Path) -> dict[str, Any]:
    return yaml.safe_load(_read(workspace, "workspace.yaml"))


def load_catalog_payload(
    workspace: Path,
    *,
    candidate_document: str | None = None,
    full_descriptors: bool = False,
    strip_descriptor_fields: tuple[str, ...] = (),
    strip_contract_details: bool = False,
    descriptor_profile: str | None = None,
) -> str:
    """Catalogue view shared by M2 and M3 (input parity, plan D3).

    Full descriptors for every service named in the public candidate sets,
    plus a compact index (id, category, summary) of all remaining services.
    """
    if full_descriptors:
        candidate_ids: list[str] = []
    else:
        candidates = yaml.safe_load(candidate_document or load_candidates(workspace))
        if not isinstance(candidates, dict) or not isinstance(
            candidates.get("candidate_sets"), list
        ):
            raise ValueError("candidate document is not a candidate-set mapping")
        candidate_ids = sorted(
            {
                service_id
                for candidate_set in candidates["candidate_sets"]
                for service_id in candidate_set["service_ids"]
            }
        )
    services_dir = workspace / "catalog" / "services"
    full_blocks: list[str] = []
    index_lines: list[str] = []
    for descriptor_path in sorted(services_dir.glob("*.yaml")):
        document = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
        service_id = document["service_id"]
        if full_descriptors or service_id in candidate_ids:
            for field in strip_descriptor_fields:
                document.pop(field, None)
            if strip_contract_details:
                document.pop("contracts", None)
                for port_kind in ("inputs", "outputs"):
                    for port in (document.get("interface") or {}).get(port_kind, []):
                        port.pop("schema_ref", None)
            if descriptor_profile:
                document = _descriptor_profile(document, descriptor_profile)
            full_blocks.append(yaml.safe_dump(document, sort_keys=False).strip())
        else:
            summary = document.get("capability", {}).get("summary", "")
            one_line = " ".join(str(summary).split())[:200]
            index_lines.append(
                f"- {service_id} (v{document['version']}, {document['category']}): {one_line}"
            )
    parts = [
        "# Catalog snapshot",
        f"version: {yaml.safe_load((workspace / 'catalog' / 'catalog.yaml').read_text())['version']}",
        "",
        "## Candidate service descriptors (full)",
        "\n\n---\n\n".join(full_blocks),
        "",
        "## Remaining catalog services (index only)",
        "\n".join(index_lines),
    ]
    return "\n".join(parts)


def _descriptor_profile(document: dict[str, Any], profile: str) -> dict[str, Any]:
    """Project a descriptor to a registered A11 information layer."""

    identity = {
        key: document[key]
        for key in ("service_id", "version", "display_name", "category", "capability")
        if key in document
    }
    if profile == "name_description":
        return identity
    interface = document.get("interface") or {}
    identity["interface"] = {
        "inputs": interface.get("inputs", []),
        "outputs": interface.get("outputs", []),
    }
    if profile == "artifacts":
        return identity
    identity["interface"]["parameters"] = interface.get("parameters", [])
    identity["interface"]["secrets"] = interface.get("secrets", [])
    identity["contracts"] = document.get("contracts", [])
    if profile == "parameters":
        return identity
    if profile == "policies":
        identity["lifecycle"] = document.get("lifecycle", {})
        identity["policies"] = document.get("policies", {})
        identity["compatibility"] = document.get("compatibility", {})
        return identity
    if profile == "full":
        return document
    raise ValueError(f"unknown descriptor profile: {profile!r}")


def load_fixture_previews(workspace: Path) -> str:
    fixtures_dir = workspace / "fixtures"
    previews: list[str] = []
    if not fixtures_dir.is_dir():
        return "(no fixtures)"
    files = [path for path in sorted(fixtures_dir.rglob("*")) if path.is_file()]
    for path in files[:FIXTURE_PREVIEW_MAX_FILES]:
        relative = path.relative_to(workspace)
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except (UnicodeDecodeError, ValueError):
            previews.append(f"### {relative}\n(binary file, {path.stat().st_size} bytes)")
            continue
        if len(content.encode("utf-8", errors="replace")) > FIXTURE_PREVIEW_MAX_BYTES:
            content = content[:FIXTURE_PREVIEW_MAX_BYTES] + "\n... (truncated)"
        previews.append(f"### {relative}\n{content}")
    if len(files) > FIXTURE_PREVIEW_MAX_FILES:
        previews.append(f"(... {len(files) - FIXTURE_PREVIEW_MAX_FILES} more fixture files)")
    return "\n\n".join(previews)


def load_schema(workspace: Path, name: str) -> str:
    return _read(workspace, f"schemas/{name}")


def build_visible_view(
    workspace: Path,
    method_id: str,
    *,
    ablation: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Assemble the exact prompt-visible payload for a method."""
    workspace = workspace.resolve()
    if method_id not in VISIBLE_VIEWS:
        raise ValueError(f"unknown method id: {method_id!r}")
    ablation = ablation or {}
    view: dict[str, str] = {"task": load_task(workspace)}
    if ablation:
        view["ablation_id"] = str(ablation.get("id", "unnamed_ablation"))
    scope = VISIBLE_VIEWS[method_id]
    if "candidates/" in scope:
        if ablation.get("candidate_document") is not None:
            view["candidates"] = str(ablation["candidate_document"])
        elif ablation.get("withhold_candidates"):
            view["candidates"] = "(candidate sets withheld by registered ablation)"
        else:
            view["candidates"] = load_candidates(workspace)
        stripped = tuple(str(item) for item in ablation.get("strip_descriptor_fields", []))
        if ablation.get("withhold_policies") and "policies" not in stripped:
            stripped += ("policies",)
        view["catalog"] = load_catalog_payload(
            workspace,
            candidate_document=view["candidates"],
            full_descriptors=bool(ablation.get("full_catalog")),
            strip_descriptor_fields=stripped,
            strip_contract_details=bool(ablation.get("strip_contract_details")),
            descriptor_profile=(
                str(ablation["descriptor_profile"]) if ablation.get("descriptor_profile") else None
            ),
        )
        view["candidate_instruction"] = (
            "Candidate sets are withheld. Select the best compatible active service from the full catalog."
            if ablation.get("withhold_candidates")
            else "For each source step you must use one service from its candidate set."
        )
    if "schemas/" in scope:
        view["serviceflow_schema"] = load_schema(workspace, "serviceflow_ir.schema.json")
        view["runtime_manifest_schema"] = load_schema(workspace, "runtime_manifest.schema.json")
    if "contracts/" in scope:
        view["contracts"] = (
            "(artifact contracts withheld by registered ablation)"
            if ablation.get("withhold_contracts")
            else load_contract_previews(workspace)
        )
    if "fixtures/" in scope:
        view["fixtures"] = load_fixture_previews(workspace)
    if ablation.get("unstructured_diagnostics"):
        view["diagnostic_visibility"] = "gate_identity"
    if ablation.get("diagnostic_visibility"):
        view["diagnostic_visibility"] = str(ablation["diagnostic_visibility"])
    if ablation.get("redact_diagnostic_gates"):
        view["redact_diagnostic_gates"] = tuple(
            str(gate) for gate in ablation["redact_diagnostic_gates"]
        )
    if ablation.get("repair_targeting"):
        view["repair_targeting"] = str(ablation["repair_targeting"])
    return view


def load_contract_previews(workspace: Path) -> str:
    """Public artifact contract schemas, with the exact paths schema_ref needs."""
    contracts_dir = workspace / "contracts"
    if not contracts_dir.is_dir():
        return "(no contracts)"
    blocks: list[str] = []
    for path in sorted(contracts_dir.rglob("*")):
        if path.is_file():
            relative = path.relative_to(workspace)
            blocks.append(f"### {relative}\n{path.read_text(encoding='utf-8').strip()}")
    return "\n\n".join(blocks) if blocks else "(no contracts)"


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SYSTEM_BASE = (
    "You are a service-composition engineer in an authorized offline benchmark. "
    "All runtime scripts are deterministic mocks over supplied fixtures; they "
    "must not contact or modify real services. You produce only the artifacts "
    "requested, with no commentary, preamble, or explanation. Your output must "
    "parse exactly as the requested format. Follow every supplied schema's exact "
    "types, required fields, and enum spellings; do not invent aliases. In YAML, "
    "quote string scalars containing a colon or other YAML-significant characters."
)

MULTI_FILE_FORMAT = (
    "When multiple files are requested, emit them in this exact format:\n"
    "===FILE: relative/path===\n<file content>\n\n"
    "===FILE: another/path===\n<file content>\n"
    "Every requested file must appear exactly once. Paths must be relative. "
    "Do not wrap file bodies in Markdown code fences; the FILE markers already "
    "delimit them."
)


def m0_prompts(view: dict[str, str]) -> tuple[str, str]:
    user = (
        "# Pipeline requirement\n\n"
        f"{view['task']}\n\n"
        "# Task\n\n"
        "Write an Argo Workflow (argoproj.io/v1alpha1) that implements this "
        "pipeline. Output a single YAML document (or multi-document YAML if a "
        "CronWorkflow is required by the schedule). Use container templates "
        "with python:3.12-slim images. Output only YAML."
    )
    return SYSTEM_BASE, user


def m1_stage1_prompts(view: dict[str, str]) -> tuple[str, str]:
    user = (
        "# Pipeline requirement\n\n"
        f"{view['task']}\n\n"
        "# Task (stage 1 of 2)\n\n"
        "Decompose this pipeline into a directed acyclic graph of processing "
        "steps. Output a single JSON object with exactly these keys:\n"
        '{"nodes": [{"id": "step_id", "description": "what the step does"}], '
        '"edges": [{"from": "step_id", "to": "step_id"}]}\n'
        "Use snake_case step ids. Output only JSON."
    )
    return SYSTEM_BASE, user


def m1_stage2_prompts(view: dict[str, str], dag_json: str) -> tuple[str, str]:
    user = (
        "# Pipeline requirement\n\n"
        f"{view['task']}\n\n"
        "# Step decomposition (DAG)\n\n"
        f"{dag_json}\n\n"
        "# Task (stage 2 of 2)\n\n"
        "Compile this DAG into an Argo Workflow (argoproj.io/v1alpha1) with "
        "one DAG task per node and dependencies from the edges. Use container "
        "templates with python:3.12-slim images. Output only YAML."
    )
    return SYSTEM_BASE, user


def m2_prompts(view: dict[str, str]) -> tuple[str, str]:
    user = (
        "# Pipeline requirement\n\n"
        f"{view['task']}\n\n"
        "# Service candidate sets\n\n"
        f"{view.get('candidate_instruction', 'Use the provided candidate sets.')}\n\n"
        f"{view['candidates']}\n\n"
        "# Service catalog\n\n"
        f"{view['catalog']}\n\n"
        "# Available artifact contract schemas\n\n"
        "Use these public contracts when choosing data formats and connecting "
        "service outputs to downstream inputs.\n\n"
        f"{view.get('contracts', '(none)')}\n\n"
        "# Sample input data\n\n"
        f"{view.get('fixtures', '(none)')}\n\n"
        "# Task\n\n"
        "Write an Argo Workflow (argoproj.io/v1alpha1) that implements this "
        "pipeline as a composition of catalog services. Name each template "
        "after the exact service_id it invokes. Respect service interfaces, "
        "required parameters, and policies. Output only YAML."
    )
    return SYSTEM_BASE, user


def m3_ir_prompts(view: dict[str, str], workspace_manifest: dict[str, Any]) -> tuple[str, str]:
    catalog = workspace_manifest["catalog"]
    user = (
        "# Pipeline requirement\n\n"
        f"{view['task']}\n\n"
        "# Service candidate sets\n\n"
        f"{view.get('candidate_instruction', 'Use the provided candidate sets.')}\n\n"
        f"{view['candidates']}\n\n"
        "# Service catalog\n\n"
        f"{view['catalog']}\n\n"
        "# ServiceFlowIR schema\n\n"
        f"{view['serviceflow_schema']}\n\n"
        "# Available artifact contract schemas\n\n"
        "For artifact schema_ref fields, reference these exact public paths. "
        "Do NOT copy schema:// URIs from service descriptors into schema_ref.\n\n"
        f"{view.get('contracts', '(none)')}\n\n"
        "# Task\n\n"
        "Compose the pipeline as one ServiceFlowIR JSON object that "
        "conforms to the schema above. The harness deterministically derives "
        "the runtime manifest, mock scripts, and Argo resources from this IR; "
        "do not emit runtime files or executable code.\n\n"
        "# Schema conformance pitfalls (the most common validation failures)\n"
        "- required_policy_properties expresses YOUR requirement using the IR "
        "schema's vocabulary — it is NOT copied from service descriptor "
        "policies. Descriptors use a different vocabulary (e.g. "
        "policies.idempotency: conditionally_idempotent); never transfer "
        "descriptor values into required_policy_properties.\n"
        "- required_policy_properties.idempotency must be exactly one of: "
        "required, preferred, not_required, unknown (e.g. use 'preferred' "
        "where the descriptor says 'conditionally_idempotent'). Never write "
        "'idempotent' or 'conditionally_idempotent'.\n"
        "- required_policy_properties.network_access and .secret_access must "
        "be exactly one of: forbidden, optional, required.\n"
        "- Arrays with minItems=1 must be non-empty: every service_intent "
        "needs at least one source_step_ref, one evidence entry, one output, "
        "and one effect; every binding needs at least one output_binding.\n"
        "- pipeline_id, intent_ids, artifact_ids, and system_ids must match "
        "the schema's snake_case patterns (lowercase letters, digits, "
        "underscores).\n"
        "- Use only fields defined by the schema; additional properties are "
        "rejected.\n\n"
        "- artifact.producer is null or ONE snake_case intent-id string. Use "
        "an array only when there are at least two distinct producers; never "
        "wrap a single producer in a one-item list.\n"
        "- service_intent.confidence is exactly explicit, strongly_inferred, "
        "weakly_inferred, or unresolvable. binding.confidence excludes "
        "unresolvable. Never write explicitly_inferred.\n"
        "- requirement.notes items must be JSON strings. For example: "
        "[\"Two steps: extract then load\"].\n"
        "- An artifact schema_ref is optional. Include it only when it exactly "
        "matches a listed contracts/... path; otherwise omit it. Never use a "
        "descriptor schema:// URI.\n\n"
        "- Preserve scalar types exactly. JSON requires every string, including "
        "strings containing ':', to use double quotes.\n\n"
        "Requirements:\n"
        "- catalog_snapshot: use exactly catalog_id 'serviceflow_catalog', "
        f"version '{catalog['version']}', sha256 "
        f"'{catalog['sanitized_catalog_yaml_sha256']}'.\n"
        "- One service_intent per pipeline step, each with source_step_refs "
        "matching the candidate sets' source_step_refs.\n"
        "- Bind every intent to a concrete service_id and version from its "
        "candidate set; every bound service must exist in the catalog and be "
        "lifecycle-active.\n"
        "- Bind all required inputs, outputs, parameters, and secrets "
        "declared by each service interface; artifact data types must match "
        "port data types.\n"
        "- Declare typed artifacts and control_flow edges consistent with "
        "the data flow.\n"
        "- Include source_step_accounting covering every source step.\n"
        "- For the source block, use: dataset_id 'zenodo_pipeline_descriptions', "
        "dataset_version 'v1.0.0', benchmark_id "
        f"'{workspace_manifest['instance']['benchmark_id']}', split "
        f"'{workspace_manifest['instance']['split']}', pipeline_id "
        f"'{workspace_manifest['instance']['id']}', description_path 'task.md', "
        f"description_sha256 '{workspace_manifest['task']['description_sha256']}'.\n"
        "Output one valid JSON object only, without a Markdown fence or file marker. "
        "JSON is accepted as a strict YAML-compatible serialization by the harness."
    )
    return SYSTEM_BASE, user


def m3_runtime_prompts(view: dict[str, str], ir_yaml: str) -> tuple[str, str]:
    user = (
        "# ServiceFlowIR composition\n\n"
        f"{ir_yaml}\n\n"
        "# Runtime manifest schema\n\n"
        f"{view['runtime_manifest_schema']}\n\n"
        "# Sample input data (fixtures)\n\n"
        f"{view.get('fixtures', '(none)')}\n\n"
        "# Task\n\n"
        "Produce the deterministic runtime layer for this composition as "
        "THREE OR MORE files in the multi-file format below:\n"
        "1. ===FILE: runtime/manifest.yaml=== conforming to the schema. One "
        "task per service intent (same intent_ids), script paths under "
        "scripts/, dependencies matching the control flow, and at least one "
        "scenario referencing the fixture inputs.\n"
        "2. ===FILE: runtime/scripts/NN_name.py=== mock executable per task (you may "
        "share one parameterized script across tasks). Each script must:\n"
        "   - parse arguments with argparse (it will receive the manifest "
        "task arguments verbatim; tokens like {workspace} and {fixtures} are "
        "substituted before invocation);\n"
        "   - read its declared input fixtures/artifacts from --workspace;\n"
        "   - write every produced artifact as JSON to "
        "   <workspace>/artifacts/<artifact_id>.json, conforming to the "
        "   artifact's schema_ref contract where one is declared;\n"
        "   - exit 0 on success;\n"
        "   - use only deterministic, in-process Python logic. Do not invoke "
        "subprocesses, shell commands, network clients, system identity, clocks, "
        "or randomness. Simulate such source behavior with constants or supplied "
        "fixtures instead.\n"
        "Keep mock behavior simple and deterministic.\n\n"
        f"{MULTI_FILE_FORMAT}"
    )
    return SYSTEM_BASE, user


def m4_repair_prompts(
    view: dict[str, str],
    submission_files: dict[str, str],
    diagnostics: dict[str, Any],
    *,
    diagnostic_history: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    files_block = "\n\n".join(
        f"## {path}\n{content}" for path, content in sorted(submission_files.items())
    )
    gate_summaries = []
    failed_gates = [gate for gate in diagnostics["gates"] if gate["status"] == "fail"]
    if view.get("repair_targeting") == "first_gate" and failed_gates:
        failed_gates = failed_gates[:1]
    for gate in failed_gates:
        if gate["status"] == "fail":
            redact_all = view.get("diagnostic_visibility") == "gate_identity"
            redact_gates = set(view.get("redact_diagnostic_gates", ()))
            if redact_all or gate.get("gate") in redact_gates:
                items = "  - Validation failed at this gate; no structured diagnostic codes or paths are provided."
            else:
                items = "\n".join(
                    f"  - [{d['code']}] {d['message']}" for d in gate["diagnostics"][:20]
                )
            gate_summaries.append(f"## {gate['gate']} ({gate['description']})\n{items}")
    failed_gate_names = {gate["gate"] for gate in failed_gates}
    needs_grounding = bool(failed_gate_names & {"G2", "G3", "G4"})
    grounding_block = ""
    if needs_grounding:
        grounding_block = (
            "# Service candidate sets\n\n"
            f"{view.get('candidates', '(none)')}\n\n"
            "# Service catalog\n\n"
            f"{view.get('catalog', '(none)')}\n\n"
            "# Available artifact contract schemas\n\n"
            f"{view.get('contracts', '(none)')}\n\n"
        )
    current_failures = {
        (str(item.get("code", "")), str(item.get("message", "")))
        for gate in diagnostics.get("gates", [])
        if gate.get("status") == "fail"
        for item in gate.get("diagnostics", [])
    }
    history_lines: list[str] = []
    seen_diagnostics: set[tuple[str, str, str]] = set()
    for state_index, state in enumerate(diagnostic_history or []):
        for gate in state.get("gates", []):
            if gate.get("status") != "fail":
                continue
            for item in gate.get("diagnostics", [])[:20]:
                key = (
                    str(gate.get("gate", "")),
                    str(item.get("code", "")),
                    str(item.get("message", "")),
                )
                if key in seen_diagnostics or len(history_lines) >= 60:
                    continue
                seen_diagnostics.add(key)
                state_label = (
                    "ACTIVE"
                    if (key[1], key[2]) in current_failures
                    else "PRIOR—DO NOT REINTRODUCE"
                )
                history_lines.append(
                    f"- state {state_index} [{key[0]}:{key[1]}] ({state_label}) {key[2]}"
                )
    history_block = "\n".join(history_lines) or "(no prior diagnostic states)"
    fingerprints = [
        tuple(
            (
                str(gate.get("gate", "")),
                str(item.get("code", "")),
                str(item.get("message", "")),
            )
            for gate in state.get("gates", [])
            if gate.get("status") == "fail"
            for item in gate.get("diagnostics", [])
        )
        for state in (diagnostic_history or [])
    ]
    repeated_state = bool(fingerprints and fingerprints[-1] in fingerprints[:-1])
    user = (
        "# Pipeline requirement\n\n"
        f"{view['task']}\n\n"
        f"{grounding_block}"
        "# ServiceFlowIR schema\n\n"
        f"{view['serviceflow_schema']}\n\n"
        "# Current submission\n\n"
        f"{files_block}\n\n"
        "# Deterministic validator diagnostics\n\n"
        f"First failing gate: {diagnostics['first_failing_gate']}\n\n"
        + "\n\n".join(gate_summaries)
        + "\n\n# Cumulative diagnostic history\n\n"
        + history_block
        + f"\n\nRepeated validator state detected: {'yes' if repeated_state else 'no'}"
        + "\n\n# Task\n\n"
        "Repair the submission so it passes every failed gate. Fix only what "
        "the diagnostics identify; preserve correct decisions. Do not "
        "reintroduce any PRIOR violation listed in the cumulative history. "
        "If a repeated state is detected, change the underlying structural "
        "decision instead of repeating the same edit. Re-check every "
        "changed value against the public schemas above, including exact scalar "
        "types and enum values. Return one COMPLETE corrected ServiceFlowIR "
        "as a valid JSON object only, without a file marker or Markdown fence. "
        "Use double quotes around every key and string value. The "
        "runtime package is deterministically regenerated from it."
    )
    return SYSTEM_BASE, user
