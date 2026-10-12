"""Tests for registered A10 catalog-retrieval variants."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from prompt2serviceflow.experiments.retrieval import retrieve_candidate_document
from prompt2serviceflow.experiments.workspace import build_workspace


ROOT = Path(__file__).resolve().parents[2]
INSTANCE = ROOT / "benchmark" / "instances" / "main" / "airflow_db_cleanup"


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    build_workspace(
        INSTANCE,
        tmp_path / "workspaces",
        split="main",
        benchmark_root=ROOT / "benchmark",
    )
    return tmp_path / "workspaces" / "main" / INSTANCE.name


def _fake_embedder(texts: list[str]) -> list[list[float]]:
    return [
        [
            float(text.lower().count("airflow")),
            float(text.lower().count("cleanup")),
            float(len(text) % 97 + 1),
        ]
        for text in texts
    ]


def test_bm25_retrieval_is_stable_and_top_k(workspace: Path) -> None:
    first = retrieve_candidate_document(workspace, strategy="bm25", top_k=3)
    second = retrieve_candidate_document(workspace, strategy="bm25", top_k=3)
    assert first == second
    document = yaml.safe_load(first)
    assert document["retrieval"]["strategy"] == "bm25"
    assert all(len(item["service_ids"]) == 3 for item in document["candidate_sets"])
    assert all(
        len(item["service_ids"]) == len(set(item["service_ids"]))
        for item in document["candidate_sets"]
    )


def test_embedding_and_hybrid_retrieval_use_public_shape(workspace: Path) -> None:
    for strategy in ("embedding", "hybrid"):
        rendered = retrieve_candidate_document(
            workspace,
            strategy=strategy,
            top_k=4,
            embedder=_fake_embedder,
        )
        document = yaml.safe_load(rendered)
        assert document["retrieval"]["strategy"] == strategy
        assert all(len(item["service_ids"]) == 4 for item in document["candidate_sets"])
        assert all(item["source_step_refs"] for item in document["candidate_sets"])


def test_oracle_retrieval_is_the_original_label_free_exposure(workspace: Path) -> None:
    rendered = retrieve_candidate_document(workspace, strategy="oracle")
    document = yaml.safe_load(rendered)
    assert "retrieval" not in document
    assert "required_service_id" not in rendered
    assert "labels:" not in rendered
