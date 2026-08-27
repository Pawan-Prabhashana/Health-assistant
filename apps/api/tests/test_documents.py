"""Unit tests for KB document parsing (no network, no Docker)."""

from __future__ import annotations

import pytest

from sahana_api.kb.documents import KbDocumentError, parse_document

_DOC = """---
title: Visiting Hours
source: handbook/visiting-hours
---

# Visiting Hours

Intro paragraph.

## General Hours

General hours are 11:00 to 13:00.

## ICU Hours

ICU hours are restricted.
"""


def test_parse_document_extracts_front_matter_and_sections() -> None:
    document = parse_document(_DOC)

    assert document.title == "Visiting Hours"
    assert document.source == "handbook/visiting-hours"
    assert [section.heading for section in document.sections] == [
        "Visiting Hours",
        "General Hours",
        "ICU Hours",
    ]
    assert "11:00 to 13:00" in document.sections[1].text


def test_doc_id_and_content_hash_are_stable() -> None:
    first = parse_document(_DOC)
    second = parse_document(_DOC)
    assert first.doc_id == second.doc_id
    assert first.content_hash == second.content_hash
    assert len(first.doc_id) == 16


def test_changed_body_changes_content_hash_but_not_doc_id() -> None:
    original = parse_document(_DOC)
    edited = parse_document(_DOC.replace("ICU hours are restricted.", "ICU hours changed."))
    assert edited.doc_id == original.doc_id
    assert edited.content_hash != original.content_hash


def test_missing_front_matter_raises() -> None:
    with pytest.raises(KbDocumentError):
        parse_document("# No front matter\n\nBody.")


def test_missing_required_keys_raises() -> None:
    with pytest.raises(KbDocumentError):
        parse_document("---\ntitle: Only Title\n---\n\nBody.")
