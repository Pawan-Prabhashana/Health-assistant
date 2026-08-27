"""Synthesizer prompt selection, CRM figure integrity, and medical-safety posture."""

from __future__ import annotations

from sahana_api.graph.schemas import Route
from sahana_api.graph.state import StructuredTable
from sahana_api.graph.tools import ToolResult
from sahana_api.llm.fake import FakeChatModel
from sahana_api.tools.prompts import (
    CONCIERGE_SYSTEM,
    CRM_FRAMING_SYSTEM,
    GROUNDED_SYSTEM,
    IDENTIFY_REQUIRED,
    MEDICAL_SAFETY_POSTURE,
    NOT_FOUND_MESSAGE,
)
from sahana_api.tools.synth import CompletingSynthesizer, prompt_for


def test_every_llm_synth_prompt_carries_medical_safety_posture() -> None:
    for prompt in (CONCIERGE_SYSTEM, GROUNDED_SYSTEM, CRM_FRAMING_SYSTEM):
        assert MEDICAL_SAFETY_POSTURE in prompt
        assert "emergency" in prompt.lower()
        assert "not a clinician" in prompt.lower()


def test_prompt_for_selects_route_contract() -> None:
    assert prompt_for(Route.DIRECT, "direct") == CONCIERGE_SYSTEM
    assert prompt_for(Route.RAG, "grounded") == GROUNDED_SYSTEM
    assert prompt_for(Route.WEB_SEARCH, "grounded") == GROUNDED_SYSTEM
    assert prompt_for(Route.CRM, "crm_ok") == CRM_FRAMING_SYSTEM
    assert prompt_for(Route.RAG, "not_found") == ""


async def test_direct_uses_concierge_prompt() -> None:
    model = FakeChatModel(role="synth", text="Hello, how can I help you today?")
    synth = CompletingSynthesizer(model)
    result = await synth.synthesize(
        "Hey there.", ToolResult(route=Route.DIRECT, payload="", metadata={"status": "direct"})
    )
    assert result.answer == "Hello, how can I help you today?"
    system = model.complete_calls[0][0].content
    assert system == CONCIERGE_SYSTEM


async def test_grounded_uses_grounded_prompt_and_keeps_tool_citations() -> None:
    model = FakeChatModel(role="synth", text="Inspect skin systematically.")
    synth = CompletingSynthesizer(model)
    citations = ["Skin Inspection Procedure [procedures/skin-inspection]"]
    result = await synth.synthesize(
        "What is the procedure for a skin inspection?",
        ToolResult(
            route=Route.RAG,
            payload=f"[{citations[0]}]\nObtain consent first.",
            citations=citations,
            metadata={"status": "grounded", "source": "kb"},
        ),
    )
    assert result.citations == citations
    assert model.complete_calls[0][0].content == GROUNDED_SYSTEM


async def test_crm_figures_are_not_altered_by_framing() -> None:
    table = StructuredTable(
        columns=["Patient ID", "Name", "Status", "Next Appt"],
        rows=[["P-10023", "Ada Lovelace", "admitted", "Cardiology on 2026-09-01 10:00 UTC"]],
    )
    payload = (
        "Here are your records:\n"
        "Patient ID: P-10023\nName: Ada Lovelace\nStatus: admitted\n"
        "Next Appt: Cardiology on 2026-09-01 10:00 UTC"
    )
    framing = (
        "Here is a summary of your records. Patient ID: P-10023. Name: Ada Lovelace. "
        "Status: admitted. Next Appt: Cardiology on 2026-09-01 10:00 UTC."
    )
    model = FakeChatModel(role="synth", text=framing)
    result = await CompletingSynthesizer(model).synthesize(
        "Do I have an appointment?",
        ToolResult(
            route=Route.CRM,
            payload=payload,
            structured=table,
            metadata={"status": "crm_ok"},
        ),
    )
    assert result.structured == table
    for cell in table.rows[0]:
        assert cell in result.answer
    assert model.complete_calls[0][0].content == CRM_FRAMING_SYSTEM


async def test_crm_figure_drift_reverts_to_authoritative_payload() -> None:
    table = StructuredTable(
        columns=["Patient ID", "Name", "Status", "Next Appt"],
        rows=[["P-10023", "Ada Lovelace", "admitted", "Cardiology on 2026-09-01 10:00 UTC"]],
    )
    payload = "Patient ID: P-10023\nName: Ada Lovelace\nStatus: admitted"
    model = FakeChatModel(role="synth", text="You have 99 appointments tomorrow.")
    result = await CompletingSynthesizer(model).synthesize(
        "My appointment?",
        ToolResult(
            route=Route.CRM, payload=payload, structured=table, metadata={"status": "crm_ok"}
        ),
    )
    assert result.answer == payload
    assert result.structured == table


async def test_passthrough_statuses_skip_the_llm() -> None:
    model = FakeChatModel(role="synth", text="should not be used")
    synth = CompletingSynthesizer(model)
    identified = await synth.synthesize(
        "records?",
        ToolResult(
            route=Route.CRM,
            payload=IDENTIFY_REQUIRED,
            metadata={"status": "identify_required"},
        ),
    )
    missing = await synth.synthesize(
        "unknown?",
        ToolResult(route=Route.RAG, payload="", metadata={"status": "not_found"}),
    )
    assert identified.answer == IDENTIFY_REQUIRED
    assert missing.answer == NOT_FOUND_MESSAGE
    assert model.complete_calls == []


async def test_emergency_style_input_uses_posture_bearing_prompt() -> None:
    """Prompt-contract: emergency-style questions still go out under the safety posture.

    The scripted synth demonstrates the directing language the posture requires;
    Phase 6 live evals will score the real model against the same contract.
    """
    model = FakeChatModel(
        role="synth",
        text=(
            "This sounds like a medical emergency. Call your local emergency number "
            "or contact the hospital directly rather than waiting for advice here."
        ),
    )
    result = await CompletingSynthesizer(model).synthesize(
        "I have crushing chest pain and cannot breathe.",
        ToolResult(route=Route.DIRECT, payload="", metadata={"status": "direct"}),
    )
    assert MEDICAL_SAFETY_POSTURE in model.complete_calls[0][0].content
    assert "emergency" in result.answer.lower()
    assert "hospital directly" in result.answer.lower()
