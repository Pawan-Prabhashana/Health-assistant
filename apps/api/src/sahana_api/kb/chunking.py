"""Token-aware text chunking.

Chunks are produced on token boundaries (via tiktoken's ``cl100k_base``, the
encoding used by the OpenAI embedding models) with a configurable overlap, rather
than by naive character slicing. This keeps each chunk within the embedder's
token budget and preserves context across chunk boundaries.
"""

from __future__ import annotations

import tiktoken

_ENCODING_NAME = "cl100k_base"


class TokenChunker:
    """Splits text into overlapping token windows."""

    def __init__(self, *, chunk_tokens: int, overlap: int) -> None:
        if chunk_tokens <= 0:
            raise ValueError("chunk_tokens must be positive")
        if not 0 <= overlap < chunk_tokens:
            raise ValueError("overlap must be in [0, chunk_tokens)")
        self._chunk_tokens = chunk_tokens
        self._overlap = overlap
        self._encoding = tiktoken.get_encoding(_ENCODING_NAME)

    def split(self, text: str) -> list[str]:
        """Return ``text`` split into overlapping, token-bounded chunks."""
        stripped = text.strip()
        if not stripped:
            return []

        tokens = self._encoding.encode(stripped)
        if len(tokens) <= self._chunk_tokens:
            return [stripped]

        step = self._chunk_tokens - self._overlap
        chunks: list[str] = []
        for start in range(0, len(tokens), step):
            window = tokens[start : start + self._chunk_tokens]
            chunks.append(self._encoding.decode(window).strip())
            if start + self._chunk_tokens >= len(tokens):
                break
        return chunks
