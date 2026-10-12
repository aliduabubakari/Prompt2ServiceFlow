"""Deterministic public-catalog retrieval variants for ablation A10."""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Callable

import yaml


Embedder = Callable[[list[str]], list[list[float]]]
TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return TOKEN.findall(text.lower().replace("_", " ").replace("-", " "))


def _descriptor_text(document: dict) -> str:
    capability = document.get("capability") or {}
    interface = document.get("interface") or {}
    fields: list[str] = [
        str(document.get("service_id", "")),
        str(document.get("display_name", "")),
        str(document.get("category", "")),
        str(capability.get("summary", "")),
        *map(str, capability.get("operations", [])),
        *map(str, capability.get("keywords", [])),
    ]
    for kind in ("inputs", "outputs", "parameters", "secrets"):
        for item in interface.get(kind, []) or []:
            fields.extend((str(item.get("name", "")), str(item.get("description", ""))))
    return "\n".join(fields)


def _bm25_scores(query: str, documents: list[str]) -> list[float]:
    tokenized = [_tokens(document) for document in documents]
    query_tokens = _tokens(query)
    if not tokenized:
        return []
    average_length = sum(map(len, tokenized)) / len(tokenized) or 1.0
    document_frequency = Counter(token for tokens in tokenized for token in set(tokens))
    k1, b = 1.5, 0.75
    scores = []
    for tokens in tokenized:
        frequencies = Counter(tokens)
        score = 0.0
        for token in query_tokens:
            frequency = frequencies[token]
            if not frequency:
                continue
            frequency_docs = document_frequency[token]
            inverse_document_frequency = math.log(
                1.0 + (len(tokenized) - frequency_docs + 0.5) / (frequency_docs + 0.5)
            )
            denominator = frequency + k1 * (1.0 - b + b * len(tokens) / average_length)
            score += inverse_document_frequency * frequency * (k1 + 1.0) / denominator
        scores.append(score)
    return scores


def _cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _rank(ids: list[str], scores: list[float]) -> list[str]:
    return [
        service_id
        for service_id, _ in sorted(zip(ids, scores), key=lambda item: (-item[1], item[0]))
    ]


def retrieve_candidate_document(
    workspace: Path,
    *,
    strategy: str,
    top_k: int = 5,
    embedder: Embedder | None = None,
    reciprocal_rank_constant: int = 60,
) -> str:
    """Replace curated service IDs with top-k public-catalog retrieval results.

    Candidate-set identities and source-step groupings stay fixed so A10 varies
    only service retrieval. ``oracle`` returns the original curated exposure.
    """

    candidate_path = workspace / "candidates" / "candidate_sets.yaml"
    candidates = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))
    if strategy == "oracle":
        return yaml.safe_dump(candidates, sort_keys=False)
    if strategy not in {"bm25", "embedding", "hybrid"}:
        raise ValueError(f"unknown retrieval strategy: {strategy!r}")
    if top_k < 1:
        raise ValueError("retrieval top_k must be positive")

    descriptors = [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted((workspace / "catalog" / "services").glob("*.yaml"))
    ]
    service_ids = [document["service_id"] for document in descriptors]
    document_texts = [_descriptor_text(document) for document in descriptors]
    task = (workspace / "task.md").read_text(encoding="utf-8")
    queries = [
        task + "\nRequired source steps: " + " ".join(item["source_step_refs"])
        for item in candidates["candidate_sets"]
    ]
    document_vectors: list[list[float]] | None = None
    query_vectors: list[list[float]] | None = None
    if strategy in {"embedding", "hybrid"}:
        if embedder is None:
            raise ValueError(f"{strategy} retrieval requires an embedder")
        vectors = embedder([*document_texts, *queries])
        if len(vectors) != len(document_texts) + len(queries):
            raise ValueError("embedder returned the wrong number of vectors")
        document_vectors = vectors[: len(document_texts)]
        query_vectors = vectors[len(document_texts) :]

    for index, candidate_set in enumerate(candidates["candidate_sets"]):
        lexical_rank = _rank(service_ids, _bm25_scores(queries[index], document_texts))
        if strategy == "bm25":
            ranking = lexical_rank
        else:
            assert document_vectors is not None and query_vectors is not None
            semantic_rank = _rank(
                service_ids,
                [_cosine(query_vectors[index], vector) for vector in document_vectors],
            )
            if strategy == "embedding":
                ranking = semantic_rank
            else:
                lexical_positions = {item: rank for rank, item in enumerate(lexical_rank, 1)}
                semantic_positions = {item: rank for rank, item in enumerate(semantic_rank, 1)}
                ranking = _rank(
                    service_ids,
                    [
                        1.0 / (reciprocal_rank_constant + lexical_positions[item])
                        + 1.0 / (reciprocal_rank_constant + semantic_positions[item])
                        for item in service_ids
                    ],
                )
        candidate_set["service_ids"] = ranking[: min(top_k, len(ranking))]
    candidates["retrieval"] = {
        "strategy": strategy,
        "top_k": top_k,
        "query_basis": "public task plus public source_step_refs",
    }
    return yaml.safe_dump(candidates, sort_keys=False)
