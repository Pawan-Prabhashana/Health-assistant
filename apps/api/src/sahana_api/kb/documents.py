"""Knowledge-base document loading.

KB documents are Markdown files with a small YAML-style front-matter block
carrying ``title`` and ``source``. Each document is split into sections on H2
(``## ``) headings so retrieved chunks can be attributed to a section. A stable
``doc_id`` (hash of the source) and a ``content_hash`` (hash of the body) are
computed for deterministic, idempotent ingestion.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


class KbDocumentError(ValueError):
    """Raised when a KB document is malformed (bad front-matter, missing keys)."""


@dataclass(frozen=True)
class Section:
    """A titled span of document text."""

    heading: str
    text: str


@dataclass(frozen=True)
class KbDocument:
    """A parsed KB document with its sections and content hashes."""

    doc_id: str
    title: str
    source: str
    content_hash: str
    sections: list[Section]


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Split a ``---`` front-matter block from the body. Returns (meta, body)."""
    if not text.startswith("---"):
        raise KbDocumentError("document is missing front-matter")
    lines = text.splitlines()
    closing = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if closing is None:
        raise KbDocumentError("front-matter block is not closed")

    meta: dict[str, str] = {}
    for line in lines[1:closing]:
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise KbDocumentError(f"invalid front-matter line: {line!r}")
        meta[key.strip()] = value.strip().strip('"').strip("'")

    body = "\n".join(lines[closing + 1 :]).strip()
    return meta, body


def _split_sections(body: str, default_heading: str) -> list[Section]:
    """Split ``body`` into sections on H2 headings, preserving order."""
    sections: list[Section] = []
    heading = default_heading
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            sections.append(Section(heading=heading, text=text))

    for line in body.splitlines():
        if line.startswith("## "):
            flush()
            heading = line[3:].strip()
            buffer = []
        else:
            buffer.append(line)
    flush()
    return sections


def parse_document(text: str) -> KbDocument:
    """Parse a single Markdown document into a :class:`KbDocument`."""
    meta, body = _parse_front_matter(text)
    title = meta.get("title")
    source = meta.get("source")
    if not title or not source:
        raise KbDocumentError("front-matter must include 'title' and 'source'")

    doc_id = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
    content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    sections = _split_sections(body, default_heading=title)
    if not sections:
        raise KbDocumentError(f"document has no content: {source}")
    return KbDocument(
        doc_id=doc_id,
        title=title,
        source=source,
        content_hash=content_hash,
        sections=sections,
    )


def load_documents(root: Path) -> Iterator[KbDocument]:
    """Load and parse every ``*.md`` document under ``root`` in a stable order."""
    for path in sorted(root.rglob("*.md")):
        yield parse_document(path.read_text(encoding="utf-8"))
