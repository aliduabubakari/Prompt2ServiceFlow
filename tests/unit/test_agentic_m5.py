"""Tests for M5 container tooling: staging, budget shim, proxy, assets."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from prompt2serviceflow.experiments.agentic import (
    DEFAULT_M5_AGENT_STEPS,
    METHOD_TEMPLATE,
    M5_ASSETS,
    _budget_shim,
    _classify_m5_run,
    _m5_usage_from_proxy_events,
    agent_dockerfile,
    prepare_image_context,
    stage_agent_workspace,
)
from experiments.m5.proxy import _request_shape, _response_shape
from prompt2serviceflow.experiments.workspace import build_workspace


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmark"
INSTANCE = BENCHMARK / "instances" / "main" / "airflow_db_cleanup"
FORBIDDEN = (
    "required_service_id",
    "internal_spec",
    "source_refs",
    "distractor",
    "semantic_mismatch",
    "contract_mismatch",
    "generic_escape_hatch",
    "gold/",
)


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    out = tmp_path / "ws"
    build_workspace(INSTANCE, out, split="main", benchmark_root=BENCHMARK)
    return out / "main" / INSTANCE.name


def test_method_template_no_private_vocab() -> None:
    text = METHOD_TEMPLATE.format(validator_budget=4)
    for token in FORBIDDEN:
        assert token not in text, token
    assert "{validator_budget}" not in text
    assert "at most\n  4 times" in text or "4 times" in text


def test_stage_agent_workspace(workspace: Path, tmp_path: Path) -> None:
    staged = stage_agent_workspace(workspace, tmp_path / "run", validator_budget=4)
    assert (staged / "METHOD.md").is_file()
    assert (staged / "bin" / ".validate_submission_real").is_file()
    assert (staged / "bin" / ".last_validator_status").is_file()
    shim = staged / "bin" / "validate_submission"
    assert shim.is_file() and os.access(shim, os.X_OK)
    assert "4" in shim.read_text()
    # The on-disk shared workspace is untouched.
    assert not (workspace / "METHOD.md").exists()
    assert (workspace / "bin" / "validate_submission").read_text().startswith("#!/bin/sh\n# Public")
    # Staged content carries no private vocabulary.
    for path in staged.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".yaml", ".json", ".sh", ""}:
            text = path.read_text(encoding="utf-8", errors="replace")
            for token in FORBIDDEN:
                assert token not in text, f"{token} in {path}"


def test_stage_agent_workspace_records_model_prompt_addendum(
    workspace: Path, tmp_path: Path
) -> None:
    addendum = "Every incomplete turn must perform a concrete action with a tool."
    staged = stage_agent_workspace(
        workspace,
        tmp_path / "run-addendum",
        validator_budget=4,
        prompt_addendum=addendum,
    )
    method = (staged / "METHOD.md").read_text()
    assert "Declared model compatibility instruction" in method
    assert addendum in method


def test_budget_shim_enforces_limit(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    real = bin_dir / ".validate_submission_real"
    real.write_text("#!/bin/sh\necho real-validator-called\n")
    real.chmod(0o755)
    shim = bin_dir / "validate_submission"
    shim.write_text(_budget_shim(3))
    shim.chmod(0o755)
    (bin_dir / ".validator_calls").write_text("0")

    for expected in (1, 2, 3):
        completed = subprocess.run([str(shim)], capture_output=True, text=True)
        assert completed.returncode == 0, completed.stderr
        assert "real-validator-called" in completed.stdout
        assert (bin_dir / ".last_validator_status").read_text().strip() == "0"
    blocked = subprocess.run([str(shim)], capture_output=True, text=True)
    assert blocked.returncode == 3
    assert "budget exhausted" in blocked.stderr
    assert (bin_dir / ".validator_calls").read_text().strip() == "4"
    # A blocked over-budget attempt must not overwrite the outcome of the
    # last real validator invocation.
    assert (bin_dir / ".last_validator_status").read_text().strip() == "0"


def test_budget_shim_records_failed_validator_status(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    real = bin_dir / ".validate_submission_real"
    real.write_text("#!/bin/sh\necho validation-failed\nexit 1\n")
    real.chmod(0o755)
    shim = bin_dir / "validate_submission"
    shim.write_text(_budget_shim(2))
    shim.chmod(0o755)
    (bin_dir / ".validator_calls").write_text("0")

    completed = subprocess.run([str(shim)], capture_output=True, text=True)
    assert completed.returncode == 1
    assert "validation-failed" in completed.stdout
    assert (bin_dir / ".last_validator_status").read_text().strip() == "1"


def test_m5_run_validity_classification() -> None:
    assert _classify_m5_run("completed", None) == ("valid", "completed")
    assert _classify_m5_run("validator_budget_exhausted", None) == (
        "valid",
        "validator_budget_exhausted",
    )
    assert _classify_m5_run("timeout", None) == ("valid", "timeout")
    assert _classify_m5_run("agent_step_budget_exhausted", None) == (
        "valid",
        "agent_step_budget_exhausted",
    )
    assert _classify_m5_run("model_error", "LM Link connection closed") == (
        "invalid",
        "infrastructure_error",
    )
    assert _classify_m5_run("agent_exit_137", None) == (
        "invalid",
        "infrastructure_error",
    )
    assert _classify_m5_run("model_error", "proxy token cap exceeded") == (
        "valid",
        "token_budget_exhausted",
    )
    assert _classify_m5_run(
        "model_error", '429: {"message":"p2sf proxy token budget exhausted"}'
    ) == ("valid", "token_budget_exhausted")


def test_m5_proxy_usage_records_provider_cost() -> None:
    from prompt2serviceflow.experiments.llm import ModelConfig

    events = [
        {
            "event": "completion",
            "tokens_spent_cumulative": 15,
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "estimated_cost": 0.0123,
                "completion_tokens_details": {"reasoning_tokens": 2},
            },
        }
    ]
    usage = _m5_usage_from_proxy_events(
        events,
        ModelConfig(model_id="m", model_name="m"),
        latency_s=1.25,
    )
    assert usage["cost_usd"] == pytest.approx(0.0123)
    assert usage["cost_source"] == "provider_usage"
    assert usage["reasoning_tokens"] == 2


def test_m5_proxy_usage_computes_cost_from_roster_prices() -> None:
    from prompt2serviceflow.experiments.llm import ModelConfig

    events = [
        {
            "event": "completion",
            "tokens_spent_cumulative": 150,
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }
    ]
    usage = _m5_usage_from_proxy_events(
        events,
        ModelConfig(
            model_id="m",
            model_name="m",
            input_price_per_mtok=1.0,
            output_price_per_mtok=2.0,
        ),
        latency_s=2.5,
    )
    assert usage["cost_usd"] == pytest.approx(0.0002)
    assert usage["cost_source"] == "configured_token_prices"


def test_agent_dockerfile_contents() -> None:
    dockerfile = agent_dockerfile()
    assert "pi-coding-agent@0.82.0" in dockerfile
    assert "pip install --no-cache-dir ." in dockerfile
    assert "COPY pkg/schemas /usr/local/lib/python3.12/schemas" in dockerfile
    assert 'ENTRYPOINT ["node", "/opt/p2sf/agent_driver.mjs"]' in dockerfile
    assert "EXPOSE" not in dockerfile  # agent publishes nothing


def test_prepare_image_context(tmp_path: Path) -> None:
    prepare_image_context(tmp_path / "ctx")
    assert (tmp_path / "ctx" / "Dockerfile").is_file()
    assert (tmp_path / "ctx" / "pkg" / "pyproject.toml").is_file()
    assert (tmp_path / "ctx" / "pkg" / "src" / "prompt2serviceflow" / "__init__.py").is_file()
    assert (tmp_path / "ctx" / "pkg" / "schemas" / "runtime_manifest.schema.json").is_file()
    assert (tmp_path / "ctx" / "agent_driver.mjs").is_file()


def test_driver_is_syntax_valid() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    completed = subprocess.run(
        [node, "--check", str(M5_ASSETS / "agent_driver.mjs")], capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr
    driver = (M5_ASSETS / "agent_driver.mjs").read_text(encoding="utf-8")
    assert "P2SF_CONTEXT_WINDOW" in driver
    assert "P2SF_REASONING_ENABLED" in driver
    assert "reasoning: REASONING_ENABLED" in driver
    assert 'thinkingLevel: REASONING_ENABLED ? "medium" : "off"' in driver
    assert "P2SF_MAX_IDLE_CONTINUATIONS" in driver
    assert "P2SF_VALIDATOR_BUDGET" in driver
    assert "P2SF_MAX_AGENT_STEPS" in driver
    assert "agent_step_budget_exhausted" in driver
    assert f'|| "{DEFAULT_M5_AGENT_STEPS}"' in driver
    assert "controller_continuation" in driver
    assert "submission/serviceflow.yaml does not" in driver
    assert "validator_budget_exhausted" in driver
    assert "token_budget_exhausted" in driver
    assert 'transcript.end(resolve)' in driver


def test_proxy_protocol_shapes_do_not_retain_content() -> None:
    request = json.dumps(
        {
            "model": "reasoning-model",
            "stream": True,
            "messages": [{"role": "user", "content": "private prompt"}],
            "tools": [{"type": "function"}],
            "reasoning_effort": "medium",
            "max_completion_tokens": 100,
        }
    ).encode()
    request_shape = _request_shape(request)
    assert request_shape["reasoning_effort"] == "medium"
    assert request_shape["max_tokens_field"] == "max_completion_tokens"
    assert "private prompt" not in json.dumps(request_shape)

    response = (
        'data: {"choices":[{"delta":{"reasoning_content":"secret thought"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"answer","tool_calls":[{}]},'
        '"finish_reason":"tool_calls"}]}\n\n'
        "data: [DONE]\n\n"
    ).encode()
    response_shape = _response_shape(response)
    assert response_shape["reasoning_characters"] == len("secret thought")
    assert response_shape["content_characters"] == len("answer")
    assert response_shape["tool_call_fragments"] == 1
    assert "secret thought" not in json.dumps(response_shape)
    assert "answer" not in json.dumps(response_shape)


class _FakeUpstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        auth = self.headers.get("Authorization")
        type(self).last_auth = auth
        type(self).last_body = body
        payload = json.dumps(
            {
                "id": "chatcmpl-x",
                "model": "stub-model",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                        "index": 0,
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _start_server(handler) -> tuple[ThreadingHTTPServer, int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def _wait_healthz(port: int, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("proxy did not start")


def test_proxy_forwards_injects_key_and_logs(tmp_path: Path) -> None:
    upstream, upstream_port = _start_server(_FakeUpstream)
    log_path = tmp_path / "proxy.jsonl"
    env = {
        **os.environ,
        "UPSTREAM_BASE_URL": f"http://127.0.0.1:{upstream_port}/v1",
        "UPSTREAM_API_KEY": "real-secret-key",
        "LOG_PATH": str(log_path),
        "PORT": "0",
    }
    # PORT 0 unsupported by the proxy CLI; run it on a chosen free port.
    proxy_server_holder: dict[str, int] = {}
    env["PORT"] = "18787"
    process = subprocess.Popen(
        [sys.executable, str(M5_ASSETS / "proxy.py")],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    proxy_server_holder["port"] = 18787
    try:
        _wait_healthz(proxy_server_holder["port"])
        request = urllib.request.Request(
            f"http://127.0.0.1:{proxy_server_holder['port']}/v1/chat/completions",
            data=json.dumps({"model": "stub-model", "messages": []}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read())
        assert payload["usage"]["total_tokens"] == 15
        assert _FakeUpstream.last_auth == "Bearer real-secret-key"
        logs = [json.loads(line) for line in log_path.read_text().splitlines()]
        completion = next(item for item in logs if item["event"] == "completion")
        assert completion["model"] == "stub-model"
        assert completion["usage"]["total_tokens"] == 15
        assert completion["tokens_spent_cumulative"] == 15
    finally:
        process.terminate()
        process.wait(timeout=5)
        upstream.shutdown()


def test_proxy_token_cap(tmp_path: Path) -> None:
    upstream, upstream_port = _start_server(_FakeUpstream)
    log_path = tmp_path / "proxy.jsonl"
    env = {
        **os.environ,
        "UPSTREAM_BASE_URL": f"http://127.0.0.1:{upstream_port}/v1",
        "UPSTREAM_API_KEY": "real-secret-key",
        "LOG_PATH": str(log_path),
        "PORT": "18788",
        "MAX_TOTAL_TOKENS": "20",
    }
    process = subprocess.Popen(
        [sys.executable, str(M5_ASSETS / "proxy.py")],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_healthz(18788)
        body = json.dumps({"model": "stub-model", "messages": []}).encode()
        headers = {"Content-Type": "application/json"}
        for expected_status in (200, 200, 429):  # 15, 30(cum>20 blocks at >=20 after 2nd?)
            request = urllib.request.Request(
                "http://127.0.0.1:18788/v1/chat/completions", data=body, headers=headers
            )
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    status = response.status
            except urllib.error.HTTPError as exc:
                status = exc.code
            assert status == expected_status, (status, expected_status)
    finally:
        process.terminate()
        process.wait(timeout=5)
        upstream.shutdown()


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not available")
def test_shim_enforcement_inside_container(tmp_path: Path) -> None:
    """The budget shim must hold inside a real container, not just on host sh."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    real = bin_dir / ".validate_submission_real"
    real.write_text("#!/bin/sh\necho called\n")
    real.chmod(0o755)
    shim = bin_dir / "validate_submission"
    shim.write_text(_budget_shim(2))
    shim.chmod(0o755)
    (bin_dir / ".validator_calls").write_text("0")
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text('FROM busybox:1.37\nCOPY bin /bin\nENTRYPOINT ["/bin/sh"]\n')
    tag = "p2sf-m5-shim-test:latest"
    build = subprocess.run(
        ["docker", "build", "-q", "-t", tag, str(tmp_path)], capture_output=True, text=True
    )
    assert build.returncode == 0, build.stderr
    try:
        run = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "/bin/sh",
                tag,
                "-c",
                "/bin/validate_submission && /bin/validate_submission; "
                "/bin/validate_submission; echo exit=$?",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert "called" in run.stdout
        assert "budget exhausted" in run.stderr
        assert "exit=3" in run.stdout
    finally:
        subprocess.run(["docker", "rmi", "-f", tag], capture_output=True)
