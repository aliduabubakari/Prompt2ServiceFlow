"""LLM client layer for method implementations (M0-M5).

The LLM exists only inside the method boundary: it generates candidate
artifacts. Validation, scoring, workspace construction, and sanitization are
LLM-free by design (see plan_experiement_evals.md and the experiments README).

Conventions:

- OpenAI-compatible chat completions; provider selected via ``base_url``.
- API keys come from environment variables (``api_key_env``); keys are never
  written to configs, prompts, logs, or run manifests.
- Every call records model, decoding settings, token usage, and latency so
  the run harness can report the cost metrics of plan Section 8.5.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class LLMError(RuntimeError):
    """Raised when an LLM call fails after retries."""


@dataclass(frozen=True)
class ModelConfig:
    """Decoding/endpoint configuration for one model (no secrets)."""

    model_id: str
    model_name: str
    base_url: str | None = None
    api_key_env: str | None = "OPENAI_API_KEY"
    max_tokens: int = 8000
    temperature: float = 0.0
    top_p: float | None = None
    seed: int | None = None
    input_price_per_mtok: float | None = None
    output_price_per_mtok: float | None = None
    request_timeout_s: float = 3600.0
    max_retries: int = 3
    context_window: int = 100_000
    reasoning: bool = False
    m5_prompt_addendum: str | None = None


def load_model_configs(config_path: Path) -> dict[str, ModelConfig]:
    """Load a model roster.

    Expected shape::

        {"models": {"<model_id>": {"model_name": ..., "base_url": ...,
         "api_key_env": "OPENAI_API_KEY", "max_tokens": 8000,
         "temperature": 0.0, ...}}}
    """
    document = json.loads(Path(config_path).read_text(encoding="utf-8"))
    roster: dict[str, ModelConfig] = {}
    for model_id, spec in document.get("models", {}).items():
        roster[model_id] = ModelConfig(
            model_id=model_id,
            model_name=spec["model_name"],
            base_url=spec.get("base_url"),
            api_key_env=spec.get("api_key_env", "OPENAI_API_KEY"),
            max_tokens=int(spec.get("max_tokens", 8000)),
            temperature=float(spec.get("temperature", 0.0)),
            top_p=spec.get("top_p"),
            seed=spec.get("seed"),
            input_price_per_mtok=spec.get("input_price_per_mtok"),
            output_price_per_mtok=spec.get("output_price_per_mtok"),
            request_timeout_s=float(spec.get("request_timeout_s", 3600.0)),
            max_retries=int(spec.get("max_retries", 3)),
            context_window=int(spec.get("context_window", 100_000)),
            reasoning=bool(spec.get("reasoning", False)),
            m5_prompt_addendum=spec.get("m5_prompt_addendum"),
        )
    return roster


@dataclass
class CompletionResult:
    text: str
    model: str
    finish_reason: str | None
    usage: dict[str, int]
    latency_s: float


@dataclass
class UsageLedger:
    """Accumulates token/latency/cost across a run (plan Section 8.5)."""

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    latency_s: float = 0.0
    validator_calls: int = 0
    evaluation_validator_calls: int = 0
    per_stage: list[dict[str, Any]] = field(default_factory=list)

    def record(self, stage: str, result: CompletionResult, config: ModelConfig) -> None:
        self.calls += 1
        self.prompt_tokens += result.usage.get("prompt_tokens", 0)
        self.completion_tokens += result.usage.get("completion_tokens", 0)
        self.reasoning_tokens += result.usage.get("reasoning_tokens", 0)
        self.total_tokens += result.usage.get("total_tokens", 0)
        self.latency_s += result.latency_s
        entry: dict[str, Any] = {
            "stage": stage,
            "model": result.model,
            "usage": result.usage,
            "latency_s": round(result.latency_s, 3),
            "finish_reason": result.finish_reason,
        }
        cost = self.estimate_cost(result.usage, config)
        if cost is not None:
            entry["cost_usd"] = cost
        self.per_stage.append(entry)

    @staticmethod
    def estimate_cost(usage: dict[str, int], config: ModelConfig) -> float | None:
        if config.input_price_per_mtok is None or config.output_price_per_mtok is None:
            return None
        return round(
            usage.get("prompt_tokens", 0) * config.input_price_per_mtok / 1e6
            + usage.get("completion_tokens", 0) * config.output_price_per_mtok / 1e6,
            6,
        )

    def summary(self, config: ModelConfig) -> dict[str, Any]:
        cost = None
        if config.input_price_per_mtok is not None and config.output_price_per_mtok is not None:
            cost = round(
                self.prompt_tokens * config.input_price_per_mtok / 1e6
                + self.completion_tokens * config.output_price_per_mtok / 1e6,
                6,
            )
        return {
            "llm_calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
            "latency_s": round(self.latency_s, 3),
            "validator_calls": self.validator_calls,
            "evaluation_validator_calls": self.evaluation_validator_calls,
            "cost_usd": cost,
            "per_stage": self.per_stage,
        }


class LLMClient(Protocol):
    """Minimal client protocol used by method runners."""

    def complete(self, *, stage: str, system: str, user: str) -> CompletionResult: ...


class OpenAICompatibleClient:
    """OpenAI-compatible chat client with simple retry/backoff."""

    def __init__(
        self, config: ModelConfig, ledger: UsageLedger, max_retries: int | None = None
    ) -> None:
        from openai import OpenAI

        api_key = os.environ.get(config.api_key_env) if config.api_key_env else "lm-studio"
        if config.api_key_env and not api_key:
            raise LLMError(
                f"environment variable {config.api_key_env} is not set; "
                "it must hold the API key for the configured provider"
            )
        self._client = OpenAI(
            api_key=api_key,
            base_url=config.base_url,
            timeout=config.request_timeout_s,
        )
        self.config = config
        self.ledger = ledger
        self.max_retries = config.max_retries if max_retries is None else max_retries

    def complete(self, *, stage: str, system: str, user: str) -> CompletionResult:
        kwargs: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }
        if self.config.top_p is not None:
            kwargs["top_p"] = self.config.top_p
        if self.config.seed is not None:
            kwargs["seed"] = self.config.seed
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            started = time.monotonic()
            try:
                response = self._client.chat.completions.create(**kwargs)
                choice = response.choices[0]
                usage = (
                    {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                        "reasoning_tokens": (
                            getattr(response.usage.completion_tokens_details, "reasoning_tokens", 0)
                            if getattr(response.usage, "completion_tokens_details", None)
                            else 0
                        ),
                    }
                    if response.usage
                    else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                )
                result = CompletionResult(
                    text=choice.message.content or "",
                    model=response.model or self.config.model_name,
                    finish_reason=choice.finish_reason,
                    usage=usage,
                    latency_s=time.monotonic() - started,
                )
                self.ledger.record(stage, result, self.config)
                return result
            except Exception as exc:  # transient provider errors
                last_error = exc
                time.sleep(min(2**attempt, 8))
        raise LLMError(f"LLM call failed after {self.max_retries} attempts: {last_error}")


class StubLLMClient:
    """Deterministic scripted client for tests (no network).

    ``script`` maps a stage name to either a fixed string or a callable
    ``(system, user) -> str``. ``default`` is used when no stage matches.
    """

    def __init__(
        self,
        config: ModelConfig | None = None,
        ledger: UsageLedger | None = None,
        script: dict[str, Any] | None = None,
        default: str = "",
    ) -> None:
        self.config = config or ModelConfig(model_id="stub", model_name="stub-model")
        self.ledger = ledger or UsageLedger()
        self.script = script or {}
        self.default = default
        self.calls_seen: list[dict[str, str]] = []

    def complete(self, *, stage: str, system: str, user: str) -> CompletionResult:
        self.calls_seen.append({"stage": stage, "system": system, "user": user})
        payload = self.script.get(stage, self.default)
        text = payload(system, user) if callable(payload) else str(payload)
        tokens = max(1, len(text) // 4)
        result = CompletionResult(
            text=text,
            model=self.config.model_name,
            finish_reason="stop",
            usage={
                "prompt_tokens": max(1, (len(system) + len(user)) // 4),
                "completion_tokens": tokens,
                "total_tokens": max(1, (len(system) + len(user)) // 4) + tokens,
            },
            latency_s=0.0,
        )
        self.ledger.record(stage, result, self.config)
        return result
