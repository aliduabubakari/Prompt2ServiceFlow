"""M5 container tooling: per-instance agent images, proxy, and session runner.

Implements the M5 protocol of plan Sections 7 and 11. The Pi agent runs
*inside* a per-instance container whose filesystem contains only the
submission workspace; the real model API key never enters the agent
container (a host-side proxy injects it upstream). The validator-call budget
is hard-enforced by a shim inside the container, and every tool call and
proxy request is logged for the run manifest.

Isolation model:

- Agent container: per-instance image (Python runtime + Node + Pi + the
  prompt2serviceflow package), attached only to a run-local *internal*
  Docker network (no outbound route). A run-local staged copy of the
  workspace is bind-mounted at ``/workspace``; the agent cannot reach the
  repository, benchmark gold, or evaluation directories because they do not
  exist in the container.
- Proxy container: attached to both the internal network and the default
  bridge (so it can reach the provider). It forwards chat completions,
  injects the real API key, logs every request/response, and enforces an
  optional cumulative-token cap.

Budget enforcement:

- ``bin/validate_submission`` inside the staged workspace is replaced by a
  shim that counts invocations and refuses beyond ``validator_budget``
  (matched to M4: initial + B repairs). ``bin/compile`` is unbudgeted.
- Wall-clock timeout and a container memory cap backstop the run.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from prompt2serviceflow.experiments import prompts
from prompt2serviceflow.experiments.harness import _file_sha256, _git_revision, _write_json
from prompt2serviceflow.experiments.llm import ModelConfig
from prompt2serviceflow.experiments.scoring import score_submission
from prompt2serviceflow.experiments.runtime_compiler import RUNTIME_COMPILER_VERSION
from prompt2serviceflow.experiments.submission import validate_submission

M5_VERSION = "2.1.4"
M5_PROMPT_VERSION = "1.0.0"
PI_PACKAGE = "@earendil-works/pi-coding-agent"
PI_VERSION = "0.82.0"
DEFAULT_M5_TOKEN_CAP = 750_000
DEFAULT_M5_TIMEOUT_SECONDS = 1800
DEFAULT_M5_IDLE_CONTINUATIONS = 3
DEFAULT_M5_AGENT_STEPS = 12
M5_AGENT_CONTEXT_POLICY = "per_model"
NODE_IMAGE = "node:22-bookworm-slim"
BASE_IMAGE = "python:3.12-slim"
PROXY_PORT = 8787
REPO_ROOT = Path(__file__).resolve().parents[3]
M5_ASSETS = REPO_ROOT / "experiments" / "m5"

AGENT_IMAGE_TAG = "p2sf-m5-agent"
PROXY_IMAGE_TAG = "p2sf-m5-proxy"


class M5Error(RuntimeError):
    """Raised when M5 orchestration fails."""


def _classify_m5_run(stopping_reason: str, last_assistant_error: str | None) -> tuple[str, str]:
    """Classify whether an M5 observation is scientifically recordable.

    Declared wall-clock, token, validator, and protocol limits are valid
    experimental stopping outcomes. Container/provider failures are not model
    composition outcomes and must be rerun instead of entering result tables.
    """

    error = (last_assistant_error or "").lower()
    if stopping_reason == "model_error" and "token" in error and (
        "cap" in error or "budget exhausted" in error
    ):
        return "valid", "token_budget_exhausted"
    if stopping_reason == "model_error" or stopping_reason.startswith("agent_exit_"):
        return "invalid", "infrastructure_error"
    return "valid", stopping_reason


# ---------------------------------------------------------------------------
# Staging
# ---------------------------------------------------------------------------

METHOD_TEMPLATE = """# M5: Agentic/tool-using service composition

You are an autonomous service-composition agent working inside an isolated
workspace. Your goal: produce a **valid service composition** for the pipeline
described in `task.md`, using the governed service catalog in `catalog/`.
This is an authorized offline benchmark. ServiceFlowIR is the benchmark's
normalized submission format; author it directly using the available tools.
You are not following Prompt2ServiceFlow's staged generation pipeline or its
gate-local repair controller. Runtime packaging is a deterministic projection
of the submitted IR; you do not write executable code.

## What you may use

- `task.md` — the pipeline requirement (read it first).
- `candidates/candidate_sets.yaml` — for each pipeline source step, the set of
  candidate services you must choose from.
- `catalog/` — the service catalog snapshot (full descriptors for candidate
  services in the main body of `catalog/catalog.yaml`'s service files; see
  `catalog/services/`). Respect interfaces, contracts, policies, and
  lifecycle status.
- `contracts/` — JSON schemas that produced artifacts must conform to.
- `schemas/serviceflow_ir.schema.json` — the source-document schema.
- `fixtures/` — public sample inputs for representative execution.
- `workspace.yaml` — workspace manifest. For `catalog_snapshot` in your IR,
  use `catalog.version` and `catalog.sanitized_catalog_yaml_sha256` from it.

## What you must produce (write only under `submission/`)

```
submission/
  serviceflow.yaml        # conforms to schemas/serviceflow_ir.schema.json
```

After writing or repairing `serviceflow.yaml`, run `bin/compile --workspace .`.
It deterministically regenerates `submission/runtime/` and `submission/argo/`
from the IR and public contracts. Never edit those derived directories.

## Tools and budget

- `bin/validate_submission --workspace .` — public deterministic validation
  (gates G0-G5 plus executability). **You may call it at most
  {validator_budget} times.** It currently shows: use it deliberately —
  inspect and reason before validating, and fix everything a report
  identifies before calling it again. Diagnostics never include assertion
  outcomes.
- `bin/compile --workspace .` — deterministic IR-to-runtime-and-Argo projection
  (unbudgeted). Run it before every validator call.

## Rules

- Work only inside this workspace. There is nothing else on this machine.
- Choose services only from the candidate sets; every bound service must
  exist in the catalog at the bound version and be lifecycle-active.
- Read the ServiceFlowIR schema before writing. Follow its exact types,
  required fields, and enum spellings. Quote YAML strings containing a colon or other
  YAML-significant characters; do not let a string parse as a mapping.
- Use the exact source identity recorded by `workspace.yaml`: dataset_id
  `zenodo_pipeline_descriptions`, dataset_version `v1.0.0`, the recorded
  benchmark_id/split/instance id, description_path `task.md`, and the recorded
  task description SHA-256. Use the workspace catalog version and sanitized
  catalog SHA-256 exactly.
- Evidence source must be `description`. IR policy values use the IR schema's
  vocabulary, not descriptor vocabulary: idempotency is one of
  `required|preferred|not_required|unknown`; network/secret access is one of
  `forbidden|optional|required`.
- Artifact `schema_ref` values, when present, must be exact paths that exist
  below `contracts/`. Never copy a descriptor's `schema://...` URI. If the
  workspace exposes no matching artifact contract, omit the optional
  `schema_ref` instead of inventing one.
- Before writing, ensure all required arrays/objects are present, every
  `minItems: 1` collection is non-empty, and YAML strings containing `:` are
  quoted. Write the complete file once; prefer one deliberate rewrite over
  repeated single-line edits.
- Use bounded inspection: read `task.md`, candidate sets, the IR schema, and
  `workspace.yaml` first; then inspect only descriptors named in the relevant
  candidate sets and only contract files referenced by those descriptors.
- Work in this order: (1) write a complete IR early, (2) compile it, (3) run
  the validator, (4) repair the IR from all diagnostics, and repeat. Do not
  spend the run exhaustively browsing before creating the first IR.
- Treat `bin/compile` and `bin/validate_submission` as opaque public tools.
  Do not inspect their scripts, installed package source, or implementation;
  invoke them and act only on their documented output.
- When `bin/validate_submission` reports `overall: pass`, or your validator
  budget is exhausted, stop: summarize what you produced and finish.
- If validation fails and calls remain, inspect every reported diagnostic,
  repair the files, and validate again. Do not stop after a failed validation
  while validator calls remain.
- Do not stop merely because the task is large. Before finishing, you MUST
  write `submission/serviceflow.yaml`, invoke `bin/compile --workspace .`, then
  invoke `bin/validate_submission --workspace .` at least once. If these minimum
  actions are incomplete, continue working instead of returning an apology.
"""


def _budget_shim(budget: int) -> str:
    return (
        "#!/bin/sh\n"
        "# Budget-enforcing shim over the real validate_submission tool.\n"
        'COUNT_FILE="$(dirname "$0")/.validator_calls"\n'
        'STATUS_FILE="$(dirname "$0")/.last_validator_status"\n'
        'COUNT=$(( $(cat "$COUNT_FILE" 2>/dev/null || echo 0) + 1 ))\n'
        'echo $COUNT > "$COUNT_FILE"\n'
        f"if [ $COUNT -gt {budget} ]; then\n"
        f'    echo "validator budget exhausted ({budget} calls allowed for this run)" >&2\n'
        "    exit 3\n"
        "fi\n"
        '"$(dirname "$0")/.validate_submission_real" "$@"\n'
        "STATUS=$?\n"
        'echo "$STATUS" > "$STATUS_FILE"\n'
        'exit "$STATUS"\n'
    )


def stage_agent_workspace(
    workspace: Path,
    run_dir: Path,
    *,
    validator_budget: int,
) -> Path:
    """Stage a run-local agent workspace copy with M5 instrumentation.

    Adds METHOD.md and the validator budget shim (the real validator is
    preserved as ``bin/.validate_submission_real``). The on-disk shared
    workspace is never modified.
    """
    workspace = workspace.resolve()
    staged = run_dir / "agent_workspace"
    if staged.exists():
        shutil.rmtree(staged)
    shutil.copytree(workspace, staged)
    method_md = METHOD_TEMPLATE.format(validator_budget=validator_budget)
    (staged / "METHOD.md").write_text(method_md, encoding="utf-8")
    bin_dir = staged / "bin"
    real = bin_dir / "validate_submission"
    if not real.is_file():
        raise M5Error(f"workspace validator missing: {real}")
    real.rename(bin_dir / ".validate_submission_real")
    shim = bin_dir / "validate_submission"
    shim.write_text(_budget_shim(validator_budget), encoding="utf-8")
    shim.chmod(0o755)
    (bin_dir / ".validator_calls").write_text("0", encoding="utf-8")
    (bin_dir / ".last_validator_status").write_text("", encoding="utf-8")
    return staged


# ---------------------------------------------------------------------------
# Image definitions and builds
# ---------------------------------------------------------------------------


def agent_dockerfile() -> str:
    return f"""FROM {BASE_IMAGE}
COPY --from={NODE_IMAGE} /usr/local /usr/local
WORKDIR /opt/p2sf
# Local install: ESM imports from agent_driver.mjs resolve /opt/p2sf/node_modules
# (a global npm install would not be resolvable from an arbitrary script).
RUN npm init -y >/dev/null && npm install --ignore-scripts {PI_PACKAGE}@{PI_VERSION}
WORKDIR /opt/p2sf/pkg
COPY pkg/pyproject.toml ./pyproject.toml
COPY pkg/src ./src
RUN pip install --no-cache-dir .
# The Argo compiler resolves its repository-level JSON schemas relative to
# the installed package root. Ship the public schema bundle at that exact
# runtime location so compile_submission is portable inside the image.
COPY pkg/schemas /usr/local/lib/python3.12/schemas
COPY agent_driver.mjs /opt/p2sf/agent_driver.mjs
RUN mkdir -p /opt/p2sf/agent /workspace
WORKDIR /workspace
ENTRYPOINT ["node", "/opt/p2sf/agent_driver.mjs"]
"""


def proxy_dockerfile() -> str:
    return f"""FROM {BASE_IMAGE}
COPY proxy.py /opt/p2sf/proxy.py
EXPOSE {PROXY_PORT}
ENTRYPOINT ["python", "/opt/p2sf/proxy.py"]
"""


def prepare_image_context(context_dir: Path) -> None:
    """Assemble the agent-image build context (Dockerfile + payloads)."""
    context_dir.mkdir(parents=True, exist_ok=True)
    (context_dir / "Dockerfile").write_text(agent_dockerfile(), encoding="utf-8")
    pkg = context_dir / "pkg"
    if pkg.exists():
        shutil.rmtree(pkg)
    (pkg / "src").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "pyproject.toml", pkg / "pyproject.toml")
    shutil.copytree(
        REPO_ROOT / "src" / "prompt2serviceflow",
        pkg / "src" / "prompt2serviceflow",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
    )
    shutil.copytree(REPO_ROOT / "schemas", pkg / "schemas")
    shutil.copy2(M5_ASSETS / "agent_driver.mjs", context_dir / "agent_driver.mjs")


def prepare_proxy_context(context_dir: Path) -> None:
    context_dir.mkdir(parents=True, exist_ok=True)
    (context_dir / "Dockerfile").write_text(proxy_dockerfile(), encoding="utf-8")
    shutil.copy2(M5_ASSETS / "proxy.py", context_dir / "proxy.py")


def _wait_for_proxy(proxy_name: str, timeout_s: float = 30.0) -> None:
    """Fail fast if the proxy container did not become healthy."""
    deadline = time.time() + timeout_s
    probe = (
        "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8787/healthz', timeout=2)"
    )
    while time.time() < deadline:
        completed = _docker("exec", proxy_name, "python", "-c", probe, check=False)
        if completed.returncode == 0:
            return
        time.sleep(1.0)
    logs = _docker("logs", proxy_name, check=False)
    raise M5Error(
        "proxy container did not become healthy: "
        f"{logs.stdout.strip()[-300:]} {logs.stderr.strip()[-300:]}"
    )


def _docker(
    *args: str, check: bool = True, timeout: int | None = None
) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=False, timeout=timeout
    )
    if check and completed.returncode:
        raise M5Error(
            f"docker {' '.join(args[:3])} failed ({completed.returncode}): "
            f"{completed.stderr.strip()[:500]}"
        )
    return completed


def build_images(build_root: Path) -> dict[str, str]:
    """Build (or rebuild) the agent and proxy images; return their digests."""
    agent_context = build_root / "agent_image"
    proxy_context = build_root / "proxy_image"
    prepare_image_context(agent_context)
    prepare_proxy_context(proxy_context)
    _docker(
        "build", "-q", "-t", f"{AGENT_IMAGE_TAG}:{M5_VERSION}", str(agent_context), timeout=3600
    )
    _docker("build", "-q", "-t", f"{PROXY_IMAGE_TAG}:{M5_VERSION}", str(proxy_context), timeout=600)
    return inspect_image_digests()


def inspect_image_digests() -> dict[str, str]:
    """Return immutable IDs for the exact M5 images used by a run."""

    digests = {}
    for name, tag in (("agent", AGENT_IMAGE_TAG), ("proxy", PROXY_IMAGE_TAG)):
        completed = _docker("image", "inspect", f"{tag}:{M5_VERSION}", "--format", "{{.Id}}")
        digests[name] = completed.stdout.strip()
    return digests


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def run_m5(
    *,
    workspace: Path,
    instance_dir: Path,
    model: ModelConfig,
    run_dir: Path,
    validator_budget: int = 4,
    token_cap: int = DEFAULT_M5_TOKEN_CAP,
    timeout_s: int = DEFAULT_M5_TIMEOUT_SECONDS,
    memory: str = "4g",
    build_root: Path | None = None,
    skip_image_build: bool = False,
    freeze_document: dict[str, Any] | None = None,
    freeze_errors_ignored: list[str] | None = None,
    batch_id: str | None = None,
    sample_index: int = 0,
    ablation: dict[str, Any] | None = None,
    max_idle_continuations: int = DEFAULT_M5_IDLE_CONTINUATIONS,
    agent_step_budget: int = DEFAULT_M5_AGENT_STEPS,
    roster_path: Path | None = None,
) -> dict[str, Any]:
    """Run the M5 agent on one instance and write the full run record."""
    if agent_step_budget < 1:
        raise ValueError("agent_step_budget must be at least 1")
    if validator_budget < 1:
        raise ValueError("validator_budget must be at least 1")
    if token_cap < 1 or timeout_s < 1:
        raise ValueError("M5 token and timeout limits must be positive")
    workspace = workspace.resolve()
    instance_dir = instance_dir.resolve()
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    workspace_manifest = prompts.load_workspace_manifest(workspace)
    instance_id = workspace_manifest["instance"]["id"]
    split = workspace_manifest["instance"]["split"]
    suffix = f"{int(time.time())}-{os.getpid()}"
    network = f"p2sf-m5-net-{suffix}"
    proxy_name = f"p2sf-m5-proxy-{suffix}"
    agent_name = f"p2sf-m5-agent-{suffix}"
    proxy_log = run_dir / "proxy_log.jsonl"

    manifest: dict[str, Any] = {
        "run_id": run_dir.name,
        "batch_id": batch_id,
        "sample_index": sample_index,
        "ablation": ablation,
        "harness_version": M5_VERSION,
        "prompt_version": prompts.PROMPT_VERSION,
        "runtime_compiler_version": RUNTIME_COMPILER_VERSION,
        "method": {"id": "m5", "name": "Agentic/tool-using service composition"},
        "m5_prompt_version": M5_PROMPT_VERSION,
        "pi": {"package": PI_PACKAGE, "version": PI_VERSION},
        "model": {
            "model_id": model.model_id,
            "model_name": model.model_name,
            "base_url": model.base_url,
            "temperature": model.temperature,
            "top_p": model.top_p,
            "seed": model.seed,
            "max_tokens": model.max_tokens,
            "request_timeout_s": model.request_timeout_s,
            "context_window": model.context_window,
        },
        "instance": {
            "id": instance_id,
            "split": split,
            "benchmark_id": workspace_manifest["instance"]["benchmark_id"],
        },
        "catalog": workspace_manifest["catalog"],
        "workspace_manifest_sha256": _file_sha256(workspace / "workspace.yaml"),
        "roster_sha256": _file_sha256(
            (roster_path or REPO_ROOT / "experiments" / "config" / "models.json").resolve()
        ),
        "visible_input_policy": {
            "method_view": [
                "task.md",
                "candidates/",
                "catalog/",
                "contracts/",
                "schemas/",
                "fixtures/",
                "bin/validate_submission",
                "bin/compile",
            ],
            "workspace_manifest": str(workspace / "workspace.yaml"),
        },
        "budgets": {
            "validator_calls": validator_budget,
            "token_cap": token_cap,
            "timeout_s": timeout_s,
            "max_idle_continuations": max_idle_continuations,
            "agent_steps": agent_step_budget,
            "agent_context_policy": M5_AGENT_CONTEXT_POLICY,
            "agent_context_window": model.context_window,
        },
        "environment": {
            "python": sys.version.split()[0],
            "git_revision": _git_revision(),
        },
        "started_at": datetime.now(timezone.utc).isoformat(),
        "freeze": (
            {
                "freeze_id": freeze_document.get("freeze_id"),
                "status": freeze_document.get("status"),
                "errors_ignored": freeze_errors_ignored or [],
            }
            if freeze_document
            else None
        ),
    }

    build_root = (build_root or run_dir / "image_build").resolve()
    if skip_image_build:
        digests = inspect_image_digests()
    else:
        digests = build_images(build_root)
    manifest["image_digests"] = digests

    staged = stage_agent_workspace(workspace, run_dir, validator_budget=validator_budget)
    # Docker bind-mounts create a directory for non-existent host paths:
    # touch the proxy log so the mount is a file.
    proxy_log.parent.mkdir(parents=True, exist_ok=True)
    proxy_log.touch(exist_ok=True)
    api_key = os.environ.get(model.api_key_env) if model.api_key_env else "lm-studio"
    if model.api_key_env and not api_key:
        raise M5Error(f"environment variable {model.api_key_env} is not set (proxy needs it)")

    upstream = (model.base_url or "https://api.openai.com/v1").rstrip("/")
    parsed_upstream = urlsplit(upstream)
    if parsed_upstream.hostname in {"localhost", "127.0.0.1", "::1"}:
        port = f":{parsed_upstream.port}" if parsed_upstream.port else ""
        upstream = urlunsplit(
            (
                parsed_upstream.scheme,
                f"host.docker.internal{port}",
                parsed_upstream.path,
                parsed_upstream.query,
                parsed_upstream.fragment,
            )
        )
    stopping_reason = "completed"
    run_started_monotonic = time.monotonic()
    try:
        _docker("network", "create", "--internal", network)
        _docker(
            "run",
            "-d",
            "--name",
            proxy_name,
            "--network",
            network,
            "--network-alias",
            "p2sf-proxy",
            "--memory",
            "512m",
            "--pids-limit",
            "128",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "-e",
            f"UPSTREAM_BASE_URL={upstream}",
            "-e",
            f"UPSTREAM_API_KEY={api_key}",
            "-e",
            f"MAX_TOTAL_TOKENS={token_cap}",
            "-v",
            f"{proxy_log}:/logs/proxy.jsonl",
            "-e",
            "LOG_PATH=/logs/proxy.jsonl",
            f"{PROXY_IMAGE_TAG}:{M5_VERSION}",
        )
        _docker("network", "connect", "bridge", proxy_name)
        _wait_for_proxy(proxy_name)
        completed = _docker(
            "run",
            "--name",
            agent_name,
            "--network",
            network,
            "--memory",
            memory,
            "--pids-limit",
            "256",
            "--cpus",
            "2.0",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "-v",
            f"{staged}:/workspace",
            "-e",
            f"P2SF_MODEL_NAME={model.model_name}",
            "-e",
            f"P2SF_CONTEXT_WINDOW={model.context_window}",
            "-e",
            f"P2SF_MAX_TOKENS={model.max_tokens}",
            "-e",
            f"P2SF_MAX_IDLE_CONTINUATIONS={max_idle_continuations}",
            "-e",
            f"P2SF_VALIDATOR_BUDGET={validator_budget}",
            "-e",
            f"P2SF_MAX_AGENT_STEPS={agent_step_budget}",
            "-e",
            "P2SF_PROXY_BASE=http://p2sf-proxy:8787/v1",
            "-e",
            "P2SF_PROXY_KEY=p2sf-dummy-key",
            "-e",
            "P2SF_OUTER_SANDBOX=1",
            "-e",
            "P2SF_TRANSCRIPT=/workspace/.agent/transcript.jsonl",
            f"{AGENT_IMAGE_TAG}:{M5_VERSION}",
            check=False,
            timeout=timeout_s,
        )
        (run_dir / "agent_container.log").write_text(
            f"--- stdout ---\n{completed.stdout}\n--- stderr ---\n{completed.stderr}\n",
            encoding="utf-8",
        )
        if completed.returncode:
            stopping_reason = f"agent_exit_{completed.returncode}"
    except subprocess.TimeoutExpired:
        stopping_reason = "timeout"
        logs = _docker("logs", agent_name, check=False)
        (run_dir / "agent_container.log").write_text(
            f"--- stdout ---\n{logs.stdout}\n--- stderr ---\n{logs.stderr}\n",
            encoding="utf-8",
        )
    finally:
        for name in (agent_name, proxy_name):
            _docker("rm", "-f", name, check=False)
        _docker("network", "rm", network, check=False)

    manifest["stopping_reason"] = stopping_reason
    manifest["latency_s"] = time.monotonic() - run_started_monotonic
    transcript = staged / ".agent" / "transcript.jsonl"
    if transcript.is_file():
        shutil.copy2(transcript, run_dir / "agent_transcript.jsonl")
        events = [
            json.loads(line)
            for line in (run_dir / "agent_transcript.jsonl").read_text().splitlines()
            if line.strip()
        ]
        manifest["tool_calls"] = sum(1 for e in events if e.get("type") == "tool_execution_start")
        manifest["controller_continuations"] = sum(
            1 for e in events if e.get("type") == "controller_continuation"
        )
        manifest["agent_steps"] = sum(1 for e in events if e.get("type") == "agent_step")
        manifest["transcript_events"] = len(events)
        run_end_events = [e for e in events if e.get("type") == "run_end"]
        if run_end_events:
            manifest["driver_status"] = run_end_events[-1].get("status")
            if stopping_reason != "timeout":
                stopping_reason = str(run_end_events[-1].get("status") or stopping_reason)
        assistant_events = [e for e in events if e.get("type") == "assistant_message"]
        if assistant_events:
            manifest["last_assistant_stop_reason"] = assistant_events[-1].get("stop_reason")
            manifest["last_assistant_error"] = assistant_events[-1].get("error")
    manifest["stopping_reason"] = stopping_reason
    calls_file = staged / "bin" / ".validator_calls"
    validator_attempts = int(calls_file.read_text().strip()) if calls_file.is_file() else 0
    validator_calls = min(validator_attempts, validator_budget)
    manifest["validator_calls"] = validator_calls
    manifest["validator_call_attempts"] = validator_attempts
    status_file = staged / "bin" / ".last_validator_status"
    last_validator_status = status_file.read_text().strip() if status_file.is_file() else ""
    manifest["last_validator_exit_status"] = (
        int(last_validator_status) if last_validator_status.lstrip("-").isdigit() else None
    )

    # Token accounting for M5 comes from the proxy log (the agent's LLM calls
    # do not pass through the harness UsageLedger).
    proxy_events = []
    if proxy_log.is_file():
        for line in proxy_log.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    proxy_events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    completions = [event for event in proxy_events if event.get("event") == "completion"]
    manifest["usage"] = {
        "llm_calls": len(completions),
        "total_tokens": max(
            (event.get("tokens_spent_cumulative", 0) for event in completions), default=0
        ),
        "prompt_tokens": sum(
            (event.get("usage") or {}).get("prompt_tokens", 0) for event in completions
        ),
        "completion_tokens": sum(
            (event.get("usage") or {}).get("completion_tokens", 0) for event in completions
        ),
        "reasoning_tokens": sum(
            ((event.get("usage") or {}).get("completion_tokens_details") or {}).get(
                "reasoning_tokens", 0
            )
            for event in completions
        ),
        "latency_s": manifest["latency_s"],
        "validator_calls": validator_calls,
        "evaluation_validator_calls": 0,
        "source": "proxy_log",
    }

    submission = staged / "submission"
    has_submission = submission.is_dir() and any(submission.iterdir())
    if stopping_reason == "completed" and (not has_submission or validator_calls == 0):
        stopping_reason = "incomplete_protocol"
        manifest["stopping_reason"] = stopping_reason
    run_validity, classified_reason = _classify_m5_run(
        stopping_reason, manifest.get("last_assistant_error")
    )
    manifest["run_validity"] = run_validity
    manifest["stopping_reason"] = classified_reason
    if has_submission:
        try:
            manifest["usage"]["evaluation_validator_calls"] += 1
            validation = validate_submission(workspace, submission)
            _write_json(run_dir / "validation.json", validation)
            manifest["usage"]["evaluation_validator_calls"] += 1
            score = score_submission(instance_dir, workspace, submission)
            _write_json(run_dir / "score.json", score)
            manifest["evaluation"] = {
                "validation": {
                    "overall_status": validation["overall_status"],
                    "first_failing_gate": validation["first_failing_gate"],
                    "gate_statuses": {g["gate"]: g["status"] for g in validation["gates"]},
                },
                "score_summary": score["summary"],
            }
        except Exception as exc:
            manifest["evaluation"] = {"error": f"evaluation failed: {exc}"}
    else:
        manifest["evaluation"] = {"status": "empty_submission"}
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(run_dir / "manifest.json", manifest)
    if run_validity != "valid":
        raise M5Error(
            "M5 inference/container infrastructure failed; observation is invalid and must be "
            f"rerun: {manifest.get('last_assistant_error') or classified_reason}"
        )
    return manifest


if __name__ == "__main__":
    sys.exit("use scripts/run_m5_agent.py")
