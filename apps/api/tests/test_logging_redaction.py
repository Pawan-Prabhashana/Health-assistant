"""Tests that PII never reaches the logs."""

from __future__ import annotations

import pytest

from sahana_api.config import Settings
from sahana_api.logging import SENSITIVE_KEYS, configure_logging, get_logger, redact_pii

RAW_PHONE = "+94771234567"
RAW_NAME = "John Doe"


def _json_settings() -> Settings:
    return Settings(app_env="production", log_level="INFO", log_json=True)


def test_redact_pii_masks_sensitive_keys() -> None:
    event = {"event": "patient.identified", "phone": RAW_PHONE, "full_name": RAW_NAME}
    redacted = redact_pii(None, "info", event)
    assert redacted["phone"] == "[redacted]"
    assert redacted["full_name"] == "[redacted]"
    assert redacted["event"] == "patient.identified"


def test_default_sensitive_keys_cover_identity_fields() -> None:
    assert {"phone", "full_name"} <= SENSITIVE_KEYS


def test_phone_and_name_absent_from_emitted_logs(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(_json_settings())
    logger = get_logger("sahana_api.test")

    logger.info("request.received", phone=RAW_PHONE, full_name=RAW_NAME, path="/patients")

    output = capsys.readouterr().out
    assert RAW_PHONE not in output
    assert RAW_NAME not in output
    assert "[redacted]" in output
    # Non-sensitive context is preserved.
    assert "/patients" in output
