"""Phone-number normalization to E.164.

Phone numbers are the patient identity key and are stored in a single canonical
form (E.164, e.g. ``+94771234567``). All inbound numbers pass through
:func:`normalize_phone`, which parses with a default region so local formats
(``0771234567``) resolve to the same canonical value as their international form.
"""

from __future__ import annotations

from typing import Annotated

import phonenumbers
from pydantic import AfterValidator

# Default region used when a number is supplied without an international prefix.
# Sahana's deployment context is Sri Lanka (+94).
DEFAULT_REGION = "LK"


class InvalidPhoneNumberError(ValueError):
    """Raised when a value cannot be parsed as a valid phone number."""


def normalize_phone(raw: str, *, default_region: str = DEFAULT_REGION) -> str:
    """Parse and normalize ``raw`` to E.164.

    :raises InvalidPhoneNumberError: if the value is not a valid phone number.
    """
    candidate = raw.strip()
    if not candidate:
        raise InvalidPhoneNumberError("phone number must not be empty")
    try:
        parsed = phonenumbers.parse(candidate, default_region)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneNumberError("phone number is not parseable") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise InvalidPhoneNumberError("phone number is not valid")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def _validate_phone(value: str) -> str:
    """Adapt :func:`normalize_phone` to raise ``ValueError`` for Pydantic."""
    try:
        return normalize_phone(value)
    except InvalidPhoneNumberError as exc:
        raise ValueError(str(exc)) from exc


# Annotated ``str`` that normalizes to E.164 during validation. Used for path and
# query parameters so an invalid number yields a 422 error envelope.
NormalizedPhone = Annotated[str, AfterValidator(_validate_phone)]
