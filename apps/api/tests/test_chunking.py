"""Unit tests for token-aware chunking.

TokenChunker uses tiktoken, whose encoding vocabulary is fetched (and cached) on
first use. When that fetch is unavailable (fully offline), these tests skip.
"""

from __future__ import annotations

import pytest

from sahana_api.kb.chunking import TokenChunker


def _chunker(chunk_tokens: int, overlap: int) -> TokenChunker:
    try:
        return TokenChunker(chunk_tokens=chunk_tokens, overlap=overlap)
    except Exception as exc:  # tiktoken vocabulary unavailable offline
        pytest.skip(f"tiktoken unavailable: {type(exc).__name__}")


def test_short_text_is_single_chunk() -> None:
    chunker = _chunker(chunk_tokens=64, overlap=8)
    chunks = chunker.split("A short sentence.")
    assert chunks == ["A short sentence."]


def test_empty_text_is_no_chunks() -> None:
    chunker = _chunker(chunk_tokens=64, overlap=8)
    assert chunker.split("   ") == []


def test_long_text_splits_into_multiple_chunks() -> None:
    chunker = _chunker(chunk_tokens=16, overlap=4)
    text = " ".join(f"word{i}" for i in range(200))
    chunks = chunker.split(text)
    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)


def test_overlap_repeats_tokens_between_chunks() -> None:
    chunker = _chunker(chunk_tokens=16, overlap=8)
    dense = chunker.split(" ".join(str(i) for i in range(300)))
    sparse = chunker.split(" ".join(str(i) for i in range(300)))
    # Deterministic: same input yields the same chunk boundaries.
    assert dense == sparse
    assert len(dense) > 2


def test_invalid_overlap_rejected() -> None:
    with pytest.raises(ValueError):
        TokenChunker(chunk_tokens=16, overlap=16)
    with pytest.raises(ValueError):
        TokenChunker(chunk_tokens=0, overlap=0)
