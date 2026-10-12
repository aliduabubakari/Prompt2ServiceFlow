#!/usr/bin/env python3
"""Pre-flight readiness check before any experiment batch.

Verify every invariant before corpus experiment runs. Exit 0 if and
only if all checks pass.

Checks:
    1. every workspace in the selected corpus scope is present
    2. leakage gate passes over every workspace
    3. for each enabled model in the roster: the configured API key env var
       is set and a minimal 1-token auth probe succeeds
    4. freeze.json is present and 'frozen'
    5. prompt2serviceflow package importable

M5 container checks are exploratory and run only with ``--include-m5``.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from shutil import which as shutil_which


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402


CORE_SPLITS = ("main", "validation")
CORPUS_SPLITS = (*CORE_SPLITS, "extension")
INSTANCE_COUNTS = {"main": 40, "validation": 20, "extension": 50}
FREEZE = PROJECT_ROOT / "experiments" / "config" / "freeze.json"
ROSTER = PROJECT_ROOT / "experiments" / "config" / "models.json"


def _check(label: str, ok: bool, detail: str = "") -> tuple[bool, str]:
    prefix = "PASS" if ok else "FAIL"
    return ok, f"[{prefix:5s}] {label}{'  ' + detail if detail else ''}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--workspaces-root",
        type=Path,
        default=PROJECT_ROOT / "experiments" / "workspaces",
    )
    parser.add_argument("--config", type=Path, default=ROSTER)
    parser.add_argument("--freeze-config", type=Path, default=FREEZE)
    parser.add_argument(
        "--scope",
        choices=("core", "corpus"),
        default="core",
        help="core checks Main-40+Validation-20; corpus also checks Extension-50",
    )
    parser.add_argument(
        "--include-m5",
        action="store_true",
        help="also verify exploratory M5 Docker images and CLI",
    )
    parser.add_argument(
        "--skip-m5",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--skip-auth", action="store_true")
    parser.add_argument(
        "--allow-unfrozen",
        action="store_true",
        help="development pilots only: check freeze consistency without requiring frozen status",
    )
    parser.add_argument(
        "--probe-completion",
        action="store_true",
        help="also send a minimal completion to each selected model",
    )
    parser.add_argument(
        "--models", nargs="*", default=None, help="model ids to auth-check (default: all in roster)"
    )
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env")

    results: list[tuple[bool, str]] = []
    workspaces_root = args.workspaces_root

    # 1. Workspace presence
    splits = CORPUS_SPLITS if args.scope == "corpus" else CORE_SPLITS
    total = sum(INSTANCE_COUNTS[split] for split in splits)
    present = 0
    for split in splits:
        for _child in sorted((workspaces_root / split).glob("*/workspace.yaml")):
            present += 1
    ok = present == total
    results.append(
        _check(
            "workspaces present", ok, f"{present}/{total} found" if not ok else f"{present}/{total}"
        )
    )

    # 2. Leakage gate
    from prompt2serviceflow.experiments.leakage import scan_workspace_root

    report = scan_workspace_root(workspaces_root)
    ok = report["status"] == "pass"
    results.append(
        _check("leakage gate", ok, f"{report['finding_count']} findings" if not ok else "")
    )

    # 3. Package importable
    try:
        importlib.import_module("prompt2serviceflow")
        importlib.import_module("prompt2serviceflow.experiments.submission")
        results.append(_check("package importable", True))
    except ImportError as exc:
        results.append(_check("package importable", False, str(exc)))

    # 4. Freeze present, frozen, and exactly consistent with code/config.
    try:
        from prompt2serviceflow.experiments.freeze import check_freeze

        freeze, freeze_errors = check_freeze(
            freeze_path=args.freeze_config,
            roster_path=args.config,
            require_frozen=not args.allow_unfrozen,
            include_m5=args.include_m5 and not args.skip_m5,
        )
        results.append(
            _check(
                "freeze consistency",
                not freeze_errors,
                "; ".join(freeze_errors) if freeze_errors else freeze.get("freeze_id", ""),
            )
        )
    except Exception as exc:
        results.append(_check("freeze consistency", False, str(exc)))

    # 5. Reproducible repository state.
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    clean = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    has_revision = revision.returncode == 0 and bool(revision.stdout.strip())
    results.append(
        _check(
            "git revision",
            has_revision or args.allow_unfrozen,
            (
                revision.stdout.strip()[:12]
                if has_revision
                else "development exception: repository has no commit"
                if args.allow_unfrozen
                else "no commit"
            ),
        )
    )
    worktree_clean = clean.returncode == 0 and not clean.stdout.strip()
    results.append(
        _check(
            "git worktree clean",
            worktree_clean or args.allow_unfrozen,
            (
                "development exception: uncommitted/untracked files present"
                if args.allow_unfrozen and not worktree_clean
                else "uncommitted/untracked files present"
                if not worktree_clean
                else ""
            ),
        )
    )

    # 6. Strong generated-code sandbox.
    if platform.system() == "Darwin":
        sandbox_ok = bool(shutil_which("sandbox-exec"))
        sandbox_detail = "macOS Seatbelt"
    else:
        image = os.environ.get("P2SF_SANDBOX_IMAGE", "python:3.12-slim")
        inspect = (
            subprocess.run(
                ["docker", "image", "inspect", image],
                capture_output=True,
                text=True,
                check=False,
            )
            if shutil_which("docker")
            else None
        )
        sandbox_ok = bool(inspect and inspect.returncode == 0)
        sandbox_detail = f"Docker image {image}"
    results.append(_check("generated-code sandbox", sandbox_ok, sandbox_detail))

    # Direct-Argo G5 is supported by an offline Argo CLI lint. Publication
    # readiness must not silently turn a missing linter into a passing gate.
    results.append(
        _check(
            "Argo CLI for direct G5",
            bool(shutil_which("argo")),
            "install Argo Workflows CLI" if not shutil_which("argo") else "",
        )
    )

    # 7. M5 images
    if args.include_m5 and not args.skip_m5:
        from prompt2serviceflow.experiments.agentic import (
            AGENT_IMAGE_TAG,
            M5_VERSION,
            PROXY_IMAGE_TAG,
        )

        agent_image = f"{AGENT_IMAGE_TAG}:{M5_VERSION}"
        proxy_image = f"{PROXY_IMAGE_TAG}:{M5_VERSION}"
        for tag, label in ((agent_image, "agent"), (proxy_image, "proxy")):
            completed = subprocess.run(
                ["docker", "image", "inspect", tag],
                capture_output=True,
                text=True,
                check=False,
            )
            ok = completed.returncode == 0
            results.append(
                _check(
                    f"M5 {label} image", ok, "missing (build via run_m5_agent.py)" if not ok else ""
                )
            )
        docker_present = shutil_which("docker")
        results.append(_check("docker CLI", bool(docker_present)))

    # 8. Endpoint/model probes
    if not args.skip_auth and args.config.is_file():
        models_doc = json.loads(args.config.read_text()).get("models", {})
        freeze_doc = (
            json.loads(args.freeze_config.read_text())
            if args.freeze_config.is_file()
            else {}
        )
        selected = set(args.models) if args.models else set(models_doc)
        for model_id in sorted(selected):
            spec = models_doc.get(model_id)
            if spec is None:
                results.append(_check(f"model {model_id}", False, "not in roster"))
                continue
            key_env = spec.get("api_key_env", "OPENAI_API_KEY")
            key = os.environ.get(key_env) if key_env else None
            if key_env and not key:
                results.append(_check(f"model {model_id}", False, f"{key_env} not set"))
                continue
            base_url = (spec.get("base_url") or "https://api.openai.com/v1").rstrip("/")
            request = urllib.request.Request(f"{base_url}/models")
            if key:
                request.add_header("Authorization", f"Bearer {key}")
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                available = {item.get("id") for item in payload.get("data", [])}
                model_ok = spec["model_name"] in available
                detail = f"{spec['model_name']} {'available' if model_ok else 'missing'}"
                if model_ok and args.probe_completion:
                    from prompt2serviceflow.experiments.llm import (
                        OpenAICompatibleClient,
                        UsageLedger,
                        load_model_configs,
                    )

                    config = load_model_configs(args.config)[model_id]
                    probe = OpenAICompatibleClient(config, UsageLedger(), max_retries=1)
                    completion = probe.complete(
                        stage="readiness_probe",
                        system="Reply with OK only.",
                        user="OK",
                    )
                    model_ok = bool(completion.text.strip())
                    detail += f"; completion model={completion.model}"
                results.append(_check(f"model {model_id}", model_ok, detail))
            except (OSError, urllib.error.URLError, json.JSONDecodeError, Exception) as exc:
                results.append(_check(f"model {model_id}", False, str(exc)[:200]))
        retrieval = freeze_doc.get("retrieval") or {}
        embedding_model = retrieval.get("embedding_model")
        endpoint = (freeze_doc.get("endpoint") or {}).get("base_url", "").rstrip("/")
        if embedding_model and endpoint and retrieval.get("runtime_probe_required", True):
            try:
                request = urllib.request.Request(f"{endpoint}/models")
                endpoint_key_env = (freeze_doc.get("endpoint") or {}).get("api_key_env")
                endpoint_key = os.environ.get(endpoint_key_env) if endpoint_key_env else None
                if endpoint_key:
                    request.add_header("Authorization", f"Bearer {endpoint_key}")
                with urllib.request.urlopen(request, timeout=10) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                available = {item.get("id") for item in payload.get("data", [])}
                results.append(
                    _check(
                        "A10 embedding model",
                        embedding_model in available,
                        f"{embedding_model} "
                        f"{'available' if embedding_model in available else 'missing'}",
                    )
                )
            except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
                results.append(_check("A10 embedding model", False, str(exc)[:200]))

    for _, line in results:
        print(line)
    failed = sum(1 for ok, _ in results if not ok)
    print(f"\n{len(results)} checks: {len(results) - failed} passed, {failed} failed")
    return min(failed, 1)


if __name__ == "__main__":
    raise SystemExit(main())
