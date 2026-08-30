// A normalised view model for an assistant turn, plus builders from the two
// sources the thread renders: a live local turn (full ChatResponse in hand) and a
// persisted history message (fields recovered from its PII-free metadata). The
// backend does not persist the CRM structured table in metadata, so a reloaded
// CRM turn shows its rendered text answer without the interactive table — the
// table is rendered live from the `final` event.

import type { ChatMessage, TableResponse, Verdict } from '../api/types';
import type { LocalTurn } from '../hooks/useChatStream';

export interface AssistantView {
  answer: string;
  verdict: Verdict | null;
  route: string | null;
  citations: string[];
  structured: TableResponse | null;
  latencyMs: number | null;
  cached: boolean;
  incomplete: boolean;
  totalTokens: number | null;
}

function asString(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' ? value : null;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : [];
}

/** Build a view from a completed live turn's ChatResponse (or its raw stream state). */
export function viewFromLocalTurn(turn: LocalTurn): AssistantView {
  const result = turn.result;
  return {
    answer: turn.answer,
    verdict: turn.verdict,
    route: turn.route,
    citations: result?.citations ?? [],
    structured: result?.structured ?? null,
    latencyMs: result?.latency_ms ?? null,
    cached: turn.verdict === 'cache_hit',
    incomplete: turn.stopped,
    totalTokens: result?.usage?.total_tokens ?? null,
  };
}

/** Build a view from a persisted assistant history message and its metadata. */
export function viewFromMessage(message: ChatMessage): AssistantView {
  const meta = message.metadata;
  const verdict = asString(meta.verdict) as Verdict | null;
  const usage = meta.usage as { total_tokens?: unknown } | undefined;
  return {
    answer: message.content,
    verdict,
    route: asString(meta.route),
    citations: asStringArray(meta.citations),
    structured: null,
    latencyMs: asNumber(meta.latency_ms),
    cached: verdict === 'cache_hit',
    incomplete: meta.incomplete === true,
    totalTokens: usage ? asNumber(usage.total_tokens) : null,
  };
}
