// Default MSW request handlers for the API surface, plus builders for the SSE
// stream endpoint. Individual tests override these with `server.use(...)` to
// exercise error states, refusals, CRM replies, and custom stream sequences.

import { http, HttpResponse } from 'msw';

import type { ChatResponse } from '../api/types';
import {
  makeAssistantMessage,
  makeChatResponse,
  makeUserMessage,
  patient,
  session,
} from './fixtures';

/** Build an SSE streaming Response from a list of pre-serialized frames. */
export function sseResponse(frames: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) {
        controller.enqueue(encoder.encode(frame));
      }
      controller.close();
    },
  });
  return new HttpResponse(stream, {
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

export const defaultHandlers = [
  http.get('/api/health/live', () => HttpResponse.json({ status: 'alive' })),
  http.get('/api/health/ready', () =>
    HttpResponse.json({ ready: true, checks: [{ name: 'postgres', ok: true, detail: null }] }),
  ),
  http.get('/api/config', () =>
    HttpResponse.json({
      app_name: 'Sahana',
      app_env: 'test',
      version: '0.1.0',
      log_level: 'INFO',
      features: {},
    }),
  ),

  http.post('/api/patients', () => HttpResponse.json(patient, { status: 201 })),
  http.get('/api/patients/by-phone/:phone', () => HttpResponse.json(patient)),
  http.get('/api/patients/:id', () => HttpResponse.json(patient)),
  http.delete('/api/patients/:id', () => new HttpResponse(null, { status: 204 })),

  http.get('/api/sessions', () => HttpResponse.json([session])),
  http.post('/api/sessions', () => HttpResponse.json(session, { status: 201 })),
  http.get('/api/sessions/:id', () => HttpResponse.json(session)),
  http.delete('/api/sessions/:id', () => new HttpResponse(null, { status: 204 })),

  http.get('/api/chat/history', () =>
    HttpResponse.json({
      session_id: session.id,
      total: 2,
      messages: [makeUserMessage(), makeAssistantMessage()],
    }),
  ),
  http.post('/api/chat', () => HttpResponse.json(makeChatResponse())),
  http.post('/api/chat/summarize', () =>
    HttpResponse.json({ session_id: session.id, summary: 'A short summary.', updated: true }),
  ),
  http.delete('/api/chat/memory', () => new HttpResponse(null, { status: 204 })),

  // A default streamed reply: routing → delta → delta → final.
  http.post('/api/chat/stream', () => sseResponse(streamFrames(makeChatResponse()))),
];

/** Frames for a typical tool-backed streamed answer ending in `final`. */
export function streamFrames(final: ChatResponse, deltas?: string[]): string[] {
  const chunks = deltas ?? splitToDeltas(final.answer);
  const frames = [
    `event: routing\ndata: ${JSON.stringify({ verdict: final.verdict, route: final.route })}\n\n`,
  ];
  for (const chunk of chunks) {
    frames.push(`event: delta\ndata: ${JSON.stringify({ text: chunk })}\n\n`);
  }
  frames.push(`event: final\ndata: ${JSON.stringify(final)}\n\n`);
  return frames;
}

function splitToDeltas(answer: string): string[] {
  const words = answer.split(' ');
  return words.map((word, index) => (index === 0 ? word : ` ${word}`));
}
