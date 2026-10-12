"""M5 model proxy: forwards chat completions, injects the real API key, logs.

Runs in the proxy container (attached to the internal agent network and the
default bridge). The agent container holds only a dummy key; this proxy
injects the real provider key upstream, logs every request/response as JSONL
(model, token usage when reported, status), and enforces an optional
cumulative-token cap (MAX_TOTAL_TOKENS) with a 429 response.

Environment:
    UPSTREAM_BASE_URL   provider base URL (e.g. https://api.deepinfra.com/v1/openai)
    UPSTREAM_API_KEY    real provider key (never reaches the agent container)
    LOG_PATH            JSONL log path (default /logs/proxy.jsonl)
    PORT                listen port (default 8787)
    MAX_TOTAL_TOKENS    cumulative cap across all forwarded calls (0 = unlimited)
"""

from __future__ import annotations

import http.client
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

UPSTREAM_BASE_URL = os.environ.get("UPSTREAM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
UPSTREAM_API_KEY = os.environ.get("UPSTREAM_API_KEY", "")
LOG_PATH = os.environ.get("LOG_PATH", "/logs/proxy.jsonl")
PORT = int(os.environ.get("PORT", "8787"))
MAX_TOTAL_TOKENS = int(os.environ.get("MAX_TOTAL_TOKENS", "0"))

_tokens_spent = 0


def _log(event: dict) -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **event}) + "\n")


def _extract_usage_from_sse(body: bytes) -> dict | None:
    """Best-effort token usage from a buffered SSE stream or plain JSON."""
    text = body.decode("utf-8", errors="replace")
    if text.lstrip().startswith("{"):
        try:
            return json.loads(text).get("usage")
        except json.JSONDecodeError:
            return None
    usage = None
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if chunk.get("usage"):
            usage = chunk["usage"]
    return usage


def _request_shape(body: bytes) -> dict:
    """Return non-content request metadata useful for compatibility diagnosis."""
    try:
        document = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"parseable": False}
    return {
        "parseable": True,
        "keys": sorted(document),
        "stream": bool(document.get("stream")),
        "message_count": len(document.get("messages") or []),
        "tool_count": len(document.get("tools") or []),
        "reasoning_effort": document.get("reasoning_effort"),
        "has_reasoning_object": "reasoning" in document,
        "max_tokens_field": next(
            (key for key in ("max_tokens", "max_completion_tokens") if key in document), None
        ),
    }


def _response_shape(body: bytes) -> dict:
    """Summarize response structure without retaining text or reasoning content."""
    text = body.decode("utf-8", errors="replace")
    documents: list[dict] = []
    if text.lstrip().startswith("{"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                documents.append(parsed)
        except json.JSONDecodeError:
            pass
    else:
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                documents.append(parsed)

    top_keys: set[str] = set()
    choice_keys: set[str] = set()
    payload_keys: set[str] = set()
    finish_reasons: set[str] = set()
    content_characters = 0
    reasoning_characters = 0
    tool_call_fragments = 0
    for document in documents:
        top_keys.update(document)
        for choice in document.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            choice_keys.update(choice)
            finish_reason = choice.get("finish_reason")
            if finish_reason is not None:
                finish_reasons.add(str(finish_reason))
            payload = choice.get("delta") or choice.get("message") or {}
            if not isinstance(payload, dict):
                continue
            payload_keys.update(payload)
            content = payload.get("content")
            if isinstance(content, str):
                content_characters += len(content)
            for key in ("reasoning", "reasoning_content"):
                reasoning = payload.get(key)
                if isinstance(reasoning, str):
                    reasoning_characters += len(reasoning)
            tool_calls = payload.get("tool_calls")
            if isinstance(tool_calls, list):
                tool_call_fragments += len(tool_calls)
    return {
        "document_count": len(documents),
        "top_level_keys": sorted(top_keys),
        "choice_keys": sorted(choice_keys),
        "payload_keys": sorted(payload_keys),
        "finish_reasons": sorted(finish_reasons),
        "content_characters": content_characters,
        "reasoning_characters": reasoning_characters,
        "tool_call_fragments": tool_call_fragments,
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # silence default stderr logging
        return

    def do_GET(self) -> None:  # noqa: N802 (stdlib API)
        if self.path.rstrip("/") == "/healthz":
            self._respond(200, b'{"status":"ok"}', "application/json")
            return
        self._respond(404, b'{"error":"not found"}', "application/json")

    def do_POST(self) -> None:  # noqa: N802 (stdlib API)
        global _tokens_spent
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        model = None
        try:
            model = json.loads(body).get("model")
        except json.JSONDecodeError:
            pass
        request_shape = _request_shape(body)
        if MAX_TOTAL_TOKENS and _tokens_spent >= MAX_TOTAL_TOKENS:
            _log({"event": "budget_exceeded", "model": model, "tokens_spent": _tokens_spent})
            self._respond(
                429,
                json.dumps(
                    {"error": {"message": "p2sf proxy token budget exhausted", "type": "budget"}}
                ).encode(),
                "application/json",
            )
            return

        # Agent calls arrive at {PROXY_BASE}/... where PROXY_BASE ends in
        # /v1; strip that prefix before appending to the upstream base (which
        # carries its own version prefix, e.g. .../v1/openai).
        path = self.path
        if path.startswith("/v1/"):
            path = path[len("/v1"):]
        upstream = urlparse(f"{UPSTREAM_BASE_URL}{path}")
        connection_class = (
            http.client.HTTPSConnection if upstream.scheme == "https" else http.client.HTTPConnection
        )
        connection = connection_class(upstream.netloc, timeout=600)
        headers = {
            "Content-Type": self.headers.get("Content-Type", "application/json"),
            "Authorization": f"Bearer {UPSTREAM_API_KEY}",
            "Accept": self.headers.get("Accept", "*/*"),
        }
        started = time.monotonic()
        try:
            connection.request("POST", upstream.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()
        except Exception as exc:
            _log({"event": "upstream_error", "model": model, "error": str(exc)})
            self._respond(502, json.dumps({"error": {"message": str(exc)}}).encode(), "application/json")
            return
        finally:
            connection.close()
        latency = round(time.monotonic() - started, 3)
        usage = _extract_usage_from_sse(payload)
        if usage and usage.get("total_tokens"):
            _tokens_spent += int(usage["total_tokens"])
        _log(
            {
                "event": "completion",
                "model": model,
                "status": response.status,
                "latency_s": latency,
                "usage": usage,
                "request_shape": request_shape,
                "response_shape": _response_shape(payload),
                "tokens_spent_cumulative": _tokens_spent,
            }
        )
        content_type = response.getheader("Content-Type") or "application/json"
        self._respond(response.status, payload, content_type)

    def _respond(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> None:
    if not UPSTREAM_API_KEY:
        raise SystemExit("UPSTREAM_API_KEY is not set")
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    _log({"event": "proxy_start", "upstream": UPSTREAM_BASE_URL, "port": PORT})
    server.serve_forever()


if __name__ == "__main__":
    main()
