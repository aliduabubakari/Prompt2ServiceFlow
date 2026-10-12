"""Output parsers and fail-closed extractors for method responses.

These utilities parse LLM responses into artifacts. They are deterministic
and deliberately unforgiving: content that cannot be parsed is recorded as a
parse failure rather than silently repaired (plan Section 8.5: "failure rate
due to parser/format violations" is a reported metric).
"""

from __future__ import annotations

import re
from typing import Any

import yaml

# Multi-file responses commonly label bodies with their source language
# (``python``, ``sh``, and so on).  Fences are presentation syntax rather
# than file content, so normalize any single-line fence label instead of
# recognizing only the structured-data languages.
FENCE_RE = re.compile(r"```[^\r\n]*\r?\n(.*?)```", re.DOTALL)
FILE_MARKER_RE = re.compile(r"^===FILE:\s*(\S+)\s*===\s*$", re.MULTILINE)
SINGLE_YAML_MARKER_RE = re.compile(
    r"^===FILE:\s*(?:serviceflow\.ya?ml)\s*(?:===)?\s*\r?\n", re.IGNORECASE
)


def extract_fenced_or_raw(text: str) -> str:
    """Return the first fenced code block, or the raw text if none exists."""
    match = FENCE_RE.search(text)
    return match.group(1).strip() if match else text.strip()


def extract_yaml_documents(text: str) -> tuple[list[Any], str | None]:
    """Parse YAML documents from a response (fenced block preferred)."""
    payload = extract_fenced_or_raw(text)
    # Some local models retain the old single-file marker despite an explicit
    # YAML-only instruction, and occasionally omit its closing ===. Removing
    # only this known presentation marker is syntax normalization, not a
    # semantic repair of the model output.
    payload = SINGLE_YAML_MARKER_RE.sub("", payload, count=1)
    try:
        documents = [doc for doc in yaml.safe_load_all(payload) if doc is not None]
    except yaml.YAMLError as exc:
        return [], f"YAML parse error: {exc}"
    if not documents:
        return [], "no YAML documents found in response"
    return documents, None


def extract_yaml_document(text: str) -> tuple[Any | None, str | None]:
    documents, error = extract_yaml_documents(text)
    if error:
        return None, error
    return documents[0], None


def extract_multi_file(text: str) -> tuple[dict[str, str], str | None]:
    """Parse a multi-file response.

    Expected format (stated in the method prompts)::

        ===FILE: relative/path===
        <file content, possibly fenced>

        ===FILE: another/path===
        <file content>

    Returns ``{path: content}``. Paths are normalized and must be relative.
    """
    files: dict[str, str] = {}
    markers = list(FILE_MARKER_RE.finditer(text))
    if not markers:
        return {}, "no ===FILE: <path>=== markers found in response"
    for index, marker in enumerate(markers):
        path = marker.group(1).strip()
        if path.startswith("/") or ".." in path.split("/"):
            return {}, f"unsafe file path in response: {path!r}"
        start = marker.end()
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        body = text[start:end].strip()
        files[path] = extract_fenced_or_raw(body) if body.startswith("```") else body
    return files, None


def extract_service_references(
    text: str, catalog_service_ids: set[str]
) -> dict[str, list[str]]:
    """Fail-closed extraction of catalog service references from text.

    A service counts as referenced only when its exact ``service_id`` appears
    as a word in the artifact (template names, images, commands, comments).
    Anything not extractable receives no credit (plan Section 6: gate
    applicability for direct-Argo methods).
    """
    references: dict[str, int] = {}
    for service_id in sorted(catalog_service_ids):
        pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(service_id)}(?![A-Za-z0-9_])")
        matches = pattern.findall(text)
        if matches:
            references[service_id] = len(matches)
    return {
        "referenced_service_ids": sorted(references),
        "reference_counts": references,
        "reference_count": len(references),
    }
