"""Streaming with usage capture and the synth stream (no network, no Docker)."""

from __future__ import annotations

from sahana_api.graph.schemas import Route
from sahana_api.graph.tools import SynthStreamEnd, ToolResult
from sahana_api.llm.base import Message, StreamCompleted, TextDelta
from sahana_api.llm.fake import FakeChatModel
from sahana_api.tools.synth import CompletingSynthesizer


async def test_stream_events_yields_deltas_then_usage() -> None:
    model = FakeChatModel(role="synth", stream_tokens=["a", "b", "c"])
    events = [event async for event in model.stream_events([Message("user", "q")])]

    deltas = [event.text for event in events if isinstance(event, TextDelta)]
    completed = [event for event in events if isinstance(event, StreamCompleted)]
    assert deltas == ["a", "b", "c"]
    assert len(completed) == 1
    assert completed[0].usage is not None
    assert completed[0].usage.total_tokens > 0


async def test_stream_text_helper_drops_usage() -> None:
    model = FakeChatModel(role="synth", stream_tokens=["x", "y"])
    tokens = [token async for token in model.stream([Message("user", "q")])]
    assert tokens == ["x", "y"]


async def test_synth_stream_grounded_yields_deltas_and_final() -> None:
    model = FakeChatModel(role="synth", stream_tokens=["Ground", "ed."])
    synth = CompletingSynthesizer(model)
    result = ToolResult(
        route=Route.RAG,
        payload="context",
        citations=["Doc [src]"],
        metadata={"status": "grounded"},
    )

    deltas: list[str] = []
    final: SynthStreamEnd | None = None
    async for item in synth.stream("What?", result):
        if isinstance(item, SynthStreamEnd):
            final = item
        else:
            deltas.append(item)

    assert deltas == ["Ground", "ed."]
    assert final is not None
    assert final.result.answer == "Grounded."
    assert final.result.citations == ["Doc [src]"]
    assert final.result.usage is not None


async def test_synth_stream_passthrough_is_single_final() -> None:
    synth = CompletingSynthesizer(FakeChatModel(role="synth"))
    result = ToolResult(route=Route.RAG, payload="", metadata={"status": "not_found"})

    items = [item async for item in synth.stream("q", result)]
    assert len(items) == 1
    assert isinstance(items[0], SynthStreamEnd)
    assert "could not find" in items[0].result.answer.lower()
