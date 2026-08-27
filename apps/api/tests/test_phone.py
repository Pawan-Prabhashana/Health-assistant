"""Unit tests for phone normalization."""

from __future__ import annotations

import pytest

from sahana_api.phone import InvalidPhoneNumberError, normalize_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+94771234567", "+94771234567"),
        ("0771234567", "+94771234567"),
        ("077 123 4567", "+94771234567"),
        ("+94 71 234 5678", "+94712345678"),
    ],
)
def test_normalize_valid_numbers(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "not-a-number", "12", "+94"])
def test_normalize_rejects_invalid(raw: str) -> None:
    with pytest.raises(InvalidPhoneNumberError):
        normalize_phone(raw)
