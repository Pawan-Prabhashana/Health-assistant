"""Unit tests for the embedder abstraction (no network, no Docker)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from sahana_api.config import Settings
from sahana_api.embeddings.base import EmbeddingError
from sahana_api.embeddings.factory import (
    build_kb_embedder,
    build_local_embedder,
    build_openai_embedder,
)
from sahana_api.embeddings.local import LocalEmbedder
from sahana_api.embeddings.openai import OpenAIEmbedder


class _FakeEmbeddings:
    async def create(self, *, model: str, input: list[str]) -> Any:
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1] * 1536) for _ in input])


class _FakeOpenAIClient:
    def __init__(self, **_kwargs: Any) -> None:
        self.embeddings = _FakeEmbeddings()


def test_local_embedder_dimension_without_download() -> None:
    embedder = LocalEmbedder()
    assert embedder.dimension == 384
    assert embedder.model_name == "sentence-transformers/all-MiniLM-L6-v2"


def test_local_embedder_rejects_unknown_model() -> None:
    with pytest.raises(EmbeddingError):
        LocalEmbedder(model="does-not-exist/model")


def test_openai_embedder_dimension_and_unknown_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sahana_api.embeddings.openai.AsyncOpenAI", _FakeOpenAIClient)
    embedder = OpenAIEmbedder(api_key="test-key")
    assert embedder.dimension == 1536
    assert embedder.model_name == "text-embedding-3-small"

    with pytest.raises(EmbeddingError):
        OpenAIEmbedder(api_key="test-key", model="nonexistent-model")


async def test_openai_embedder_embeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sahana_api.embeddings.openai.AsyncOpenAI", _FakeOpenAIClient)
    embedder = OpenAIEmbedder(api_key="test-key")

    vectors = await embedder.embed(["hello", "world"])
    assert len(vectors) == 2
    assert all(len(vector) == 1536 for vector in vectors)
    assert await embedder.embed([]) == []


def test_factory_selects_local() -> None:
    settings = Settings(kb_embedder="local")
    assert isinstance(build_kb_embedder(settings), LocalEmbedder)
    assert isinstance(build_local_embedder(settings), LocalEmbedder)


def test_factory_openai_requires_key() -> None:
    with pytest.raises(EmbeddingError):
        build_openai_embedder(Settings(openai_api_key=None))


def test_factory_selects_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sahana_api.embeddings.openai.AsyncOpenAI", _FakeOpenAIClient)
    settings = Settings(kb_embedder="openai", openai_api_key="test-key")
    assert isinstance(build_kb_embedder(settings), OpenAIEmbedder)
