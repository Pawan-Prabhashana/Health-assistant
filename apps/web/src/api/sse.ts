// Fetch-based Server-Sent Events client for `POST /chat/stream`.
//
// The browser's built-in `EventSource` is GET-only and cannot carry a request
// body, but the stream endpoint takes the message and session id in a POST body.
// So we open the stream with `fetch`, read the `ReadableStream` with a
// `TextDecoder`, parse the SSE frames ourselves, and dispatch typed events. The
// backend emits `routing` / `delta` / `final` / `error` frames and injects
// `: keepalive` comment frames on idle, which the parser skips. An
// `AbortController` cancels an in-flight stream cleanly when the user sends a new
// message or navigates away.

import { API_BASE_PATH, ApiError } from './client';
import type { ChatRequest, ChatResponse, Route, Verdict } from './types';

export interface RoutingStreamEvent {
  type: 'routing';
  verdict: Verdict;
  route: Route | null;
}
export interface DeltaStreamEvent {
  type: 'delta';
  text: string;
}
export interface FinalStreamEvent {
  type: 'final';
  data: ChatResponse;
}
export interface ErrorStreamEvent {
  type: 'error';
  code: string;
  message: string;
}

export type ChatStreamEvent =
  RoutingStreamEvent | DeltaStreamEvent | FinalStreamEvent | ErrorStreamEvent;

/** A raw parsed SSE frame: an event name and its data payload. */
export interface ServerSentEvent {
  event: string;
  data: string;
}

/**
 * Split a running buffer into complete SSE frames on the double-newline
 * delimiter, returning the parsed frames and the trailing partial remainder to
 * carry into the next read.
 */
export function splitFrames(buffer: string): { frames: string[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, '\n');
  const parts = normalized.split('\n\n');
  const rest = parts.pop() ?? '';
  return { frames: parts, rest };
}

/**
 * Parse one raw SSE frame into a {@link ServerSentEvent}. Comment frames (lines
 * beginning with `:`, used for keepalives) and frames without a data line return
 * `null` and are skipped by the iterator.
 */
export function parseFrame(frame: string): ServerSentEvent | null {
  let event = 'message';
  const dataLines: string[] = [];
  let sawData = false;
  for (const rawLine of frame.split('\n')) {
    const line = rawLine.replace(/\r$/, '');
    if (line === '' || line.startsWith(':')) {
      continue;
    }
    const colon = line.indexOf(':');
    const fieldName = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? '' : line.slice(colon + 1).replace(/^ /, '');
    if (fieldName === 'event') {
      event = value;
    } else if (fieldName === 'data') {
      dataLines.push(value);
      sawData = true;
    }
  }
  if (!sawData) {
    return null;
  }
  return { event, data: dataLines.join('\n') };
}

/** Map a raw SSE frame to a typed chat stream event, or `null` if unrecognised. */
export function toStreamEvent(sse: ServerSentEvent): ChatStreamEvent | null {
  switch (sse.event) {
    case 'routing': {
      const parsed = JSON.parse(sse.data) as { verdict: Verdict; route: Route | null };
      return { type: 'routing', verdict: parsed.verdict, route: parsed.route };
    }
    case 'delta': {
      const parsed = JSON.parse(sse.data) as { text: string };
      return { type: 'delta', text: parsed.text };
    }
    case 'final': {
      const parsed = JSON.parse(sse.data) as ChatResponse;
      return { type: 'final', data: parsed };
    }
    case 'error': {
      const parsed = JSON.parse(sse.data) as { code: string; message: string };
      return { type: 'error', code: parsed.code, message: parsed.message };
    }
    default:
      return null;
  }
}

/**
 * Read a byte stream and yield typed chat stream events. Decodes incrementally,
 * buffers across chunk boundaries, and stops cleanly when the reader is done or
 * the (optional) signal aborts.
 */
export async function* iterateStream(
  stream: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<ChatStreamEvent> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      if (signal?.aborted) {
        break;
      }
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const { frames, rest } = splitFrames(buffer);
      buffer = rest;
      for (const frame of frames) {
        const sse = parseFrame(frame);
        if (sse === null) {
          continue;
        }
        const event = toStreamEvent(sse);
        if (event !== null) {
          yield event;
        }
      }
    }
    // Flush any trailing complete frame left in the buffer at stream end.
    const tail = parseFrame(buffer);
    if (tail !== null) {
      const event = toStreamEvent(tail);
      if (event !== null) {
        yield event;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/** Open the chat SSE stream over `fetch`, returning the raw byte stream. */
export async function openChatStream(
  payload: ChatRequest,
  signal: AbortSignal,
): Promise<ReadableStream<Uint8Array>> {
  const response = await fetch(`${API_BASE_PATH}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) {
    let message = `chat stream failed with status ${response.status}`;
    let code = 'stream_error';
    try {
      const body = (await response.json()) as { error?: { code?: string; message?: string } };
      if (body.error?.message) {
        message = body.error.message;
      }
      if (body.error?.code) {
        code = body.error.code;
      }
    } catch {
      // Non-JSON error body; keep the status-derived message.
    }
    throw new ApiError(response.status, message, code);
  }
  if (response.body === null) {
    throw new ApiError(response.status, 'chat stream returned no body', 'stream_error');
  }
  return response.body;
}

/**
 * Open and consume the chat stream, invoking `onEvent` for each typed event.
 * Resolves when the stream ends; rejects on network/HTTP failure. Aborting the
 * signal ends consumption without rejecting (the caller initiated it).
 */
export async function streamChat(
  payload: ChatRequest,
  onEvent: (event: ChatStreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const stream = await openChatStream(payload, signal);
  for await (const event of iterateStream(stream, signal)) {
    onEvent(event);
  }
}
