import { describe, expect, it } from 'vitest';

import { makeChatResponse, sseFrame, streamFromChunks } from '../test/fixtures';
import type { ChatStreamEvent } from './sse';
import { iterateStream, parseFrame, splitFrames, toStreamEvent } from './sse';

describe('splitFrames', () => {
  it('splits complete frames and keeps the trailing partial as the remainder', () => {
    const { frames, rest } = splitFrames('event: a\ndata: 1\n\nevent: b\ndata: 2\n\nevent: c\nda');
    expect(frames).toEqual(['event: a\ndata: 1', 'event: b\ndata: 2']);
    expect(rest).toBe('event: c\nda');
  });

  it('normalizes CRLF line endings', () => {
    const { frames } = splitFrames('event: a\r\ndata: 1\r\n\r\n');
    expect(frames).toEqual(['event: a\ndata: 1']);
  });
});

describe('parseFrame', () => {
  it('parses an event and its data', () => {
    expect(parseFrame('event: delta\ndata: {"text":"hi"}')).toEqual({
      event: 'delta',
      data: '{"text":"hi"}',
    });
  });

  it('skips comment (keepalive) frames', () => {
    expect(parseFrame(': keepalive')).toBeNull();
  });

  it('returns null for a frame with no data line', () => {
    expect(parseFrame('event: ping')).toBeNull();
  });
});

describe('toStreamEvent', () => {
  it('maps each backend event kind to a typed event', () => {
    expect(
      toStreamEvent({ event: 'routing', data: '{"verdict":"proceed","route":"rag"}' }),
    ).toEqual({ type: 'routing', verdict: 'proceed', route: 'rag' });
    expect(toStreamEvent({ event: 'delta', data: '{"text":"hello"}' })).toEqual({
      type: 'delta',
      text: 'hello',
    });
    expect(toStreamEvent({ event: 'error', data: '{"code":"boom","message":"nope"}' })).toEqual({
      type: 'error',
      code: 'boom',
      message: 'nope',
    });
  });

  it('returns null for an unknown event name', () => {
    expect(toStreamEvent({ event: 'mystery', data: '{}' })).toBeNull();
  });
});

async function collect(
  stream: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): Promise<ChatStreamEvent[]> {
  const events: ChatStreamEvent[] = [];
  for await (const event of iterateStream(stream, signal)) {
    events.push(event);
  }
  return events;
}

describe('iterateStream', () => {
  it('yields routing, deltas, and final in order, ignoring keepalives', async () => {
    const final = makeChatResponse({ answer: 'Hi there' });
    const stream = streamFromChunks([
      sseFrame('routing', { verdict: 'proceed', route: 'direct' }),
      ': keepalive\n\n',
      sseFrame('delta', { text: 'Hi ' }),
      sseFrame('delta', { text: 'there' }),
      sseFrame('final', final),
    ]);
    const events = await collect(stream);
    expect(events.map((event) => event.type)).toEqual(['routing', 'delta', 'delta', 'final']);
    const last = events[3];
    expect(last.type === 'final' && last.data.answer).toBe('Hi there');
  });

  it('reassembles frames split across chunk boundaries', async () => {
    const stream = streamFromChunks(['event: del', 'ta\ndata: {"text":"a', 'b"}\n\n']);
    const events = await collect(stream);
    expect(events).toEqual([{ type: 'delta', text: 'ab' }]);
  });

  it('yields nothing when the signal is already aborted', async () => {
    const controller = new AbortController();
    controller.abort();
    const stream = streamFromChunks([sseFrame('delta', { text: 'x' })]);
    expect(await collect(stream, controller.signal)).toEqual([]);
  });
});
