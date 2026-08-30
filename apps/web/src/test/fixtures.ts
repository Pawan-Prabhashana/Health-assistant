// Shared test fixtures and small builders for API payloads and SSE frames.

import type { ChatMessage, ChatResponse, PatientResponse, SessionResponse } from '../api/types';

export const patient: PatientResponse = {
  id: '11111111-1111-1111-1111-111111111111',
  mrn: 'P-10023',
  phone: '+94771234567',
  full_name: 'Test Patient',
  status: 'stable',
  created_at: '2026-08-01T09:00:00Z',
};

export const session: SessionResponse = {
  id: '22222222-2222-2222-2222-222222222222',
  patient_id: patient.id,
  title: 'General enquiry',
  created_at: '2026-08-20T09:00:00Z',
  updated_at: '2026-08-20T09:05:00Z',
};

export function makeChatResponse(overrides: Partial<ChatResponse> = {}): ChatResponse {
  return {
    verdict: 'proceed',
    route: 'direct',
    answer: 'Hello, welcome to Sahana.',
    citations: [],
    structured: null,
    usage: null,
    latency_ms: 240,
    trace: [],
    ...overrides,
  };
}

export function makeAssistantMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: '33333333-3333-3333-3333-333333333333',
    role: 'assistant',
    content: 'Our visiting hours are 10am to 8pm.',
    metadata: { verdict: 'proceed', route: 'rag', latency_ms: 1700, citations: ['Visiting Hours'] },
    created_at: '2026-08-20T09:05:00Z',
    ...overrides,
  };
}

export function makeUserMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: '44444444-4444-4444-4444-444444444444',
    role: 'user',
    content: 'What are your visiting hours?',
    metadata: {},
    created_at: '2026-08-20T09:04:00Z',
    ...overrides,
  };
}

/** Serialize one SSE frame the way the backend's `format_sse` does. */
export function sseFrame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** A byte ReadableStream from a list of string chunks, for SSE-parser tests. */
export function streamFromChunks(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}
