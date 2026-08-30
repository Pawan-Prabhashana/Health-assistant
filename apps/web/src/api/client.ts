// The typed API client. Every request is rooted at `/api`, which both nginx (in
// the container topology) and the Vite dev server reverse-proxy to the FastAPI
// backend, stripping the prefix so the API receives `/health/ready`.
//
// Each of the backend's sixteen endpoints is exposed here as a typed method. The
// request and response shapes come from `./types`, which aliases the
// OpenAPI-generated `schema.d.ts`, so this client cannot silently drift from the
// Pydantic models. The SSE `POST /chat/stream` endpoint is driven from `./sse`,
// which reuses `ChatRequest` and the `ChatResponse` `final` payload from here.

import type {
  ChatHistoryResponse,
  ChatRequest,
  ChatResponse,
  ConfigResponse,
  LivenessResponse,
  PatientCreate,
  PatientResponse,
  ReadinessResponse,
  SessionCreate,
  SessionDetailResponse,
  SessionResponse,
  SummarizeResponse,
} from './types';

export const API_BASE_PATH = '/api';

/** Error raised for a non-2xx response, carrying the HTTP status and a code. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, message: string, code = 'http_error') {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

interface ErrorEnvelopeShape {
  error?: { code?: string; message?: string };
}

async function toApiError(response: Response, method: string, path: string): Promise<ApiError> {
  // The backend returns a consistent `{ error: { code, message } }` envelope for
  // handled failures; fall back to the status line for anything else.
  let code = 'http_error';
  let message = `${method} ${path} failed with status ${response.status}`;
  try {
    const body = (await response.json()) as ErrorEnvelopeShape;
    if (body.error?.message) {
      message = body.error.message;
    }
    if (body.error?.code) {
      code = body.error.code;
    }
  } catch {
    // Non-JSON error body; keep the status-derived message.
  }
  return new ApiError(response.status, message, code);
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  // `| undefined` is explicit so callers may forward an optional signal under
  // exactOptionalPropertyTypes without a conditional spread at every call site.
  signal?: AbortSignal | undefined;
  query?: Record<string, string | number | undefined> | undefined;
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = `${API_BASE_PATH}${path}`;
  if (!query) {
    return url;
  }
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) {
      params.append(key, String(value));
    }
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal, query } = options;
  const init: RequestInit = {
    method,
    headers: {
      Accept: 'application/json',
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    ...(signal ? { signal } : {}),
  };
  const response = await fetch(buildUrl(path, query), init);
  if (!response.ok) {
    throw await toApiError(response, method, path);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  // --- Health and config (3) ---
  getLiveness: (signal?: AbortSignal): Promise<LivenessResponse> =>
    request('/health/live', { signal }),
  getReadiness: (signal?: AbortSignal): Promise<ReadinessResponse> =>
    request('/health/ready', { signal }),
  getConfig: (signal?: AbortSignal): Promise<ConfigResponse> => request('/config', { signal }),

  // --- Patients (4) ---
  upsertPatient: (payload: PatientCreate, signal?: AbortSignal): Promise<PatientResponse> =>
    request('/patients', { method: 'POST', body: payload, signal }),
  getPatientById: (patientId: string, signal?: AbortSignal): Promise<PatientResponse> =>
    request(`/patients/${encodeURIComponent(patientId)}`, { signal }),
  getPatientByPhone: (phone: string, signal?: AbortSignal): Promise<PatientResponse> =>
    request(`/patients/by-phone/${encodeURIComponent(phone)}`, { signal }),
  deletePatient: (patientId: string, signal?: AbortSignal): Promise<void> =>
    request(`/patients/${encodeURIComponent(patientId)}`, { method: 'DELETE', signal }),

  // --- Sessions (4) ---
  createSession: (payload: SessionCreate, signal?: AbortSignal): Promise<SessionResponse> =>
    request('/sessions', { method: 'POST', body: payload, signal }),
  listSessions: (
    query: { phone?: string; patient_id?: string; limit?: number; offset?: number },
    signal?: AbortSignal,
  ): Promise<SessionResponse[]> => request('/sessions', { query, signal }),
  getSession: (
    sessionId: string,
    include?: 'messages',
    signal?: AbortSignal,
  ): Promise<SessionDetailResponse> =>
    request(`/sessions/${encodeURIComponent(sessionId)}`, {
      ...(include ? { query: { include } } : {}),
      signal,
    }),
  deleteSession: (sessionId: string, signal?: AbortSignal): Promise<void> =>
    request(`/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE', signal }),

  // --- Chat (5) --- (`POST /chat/stream` is driven from ./sse)
  chat: (payload: ChatRequest, signal?: AbortSignal): Promise<ChatResponse> =>
    request('/chat', { method: 'POST', body: payload, signal }),
  getHistory: (
    query: { session_id: string; limit?: number; offset?: number },
    signal?: AbortSignal,
  ): Promise<ChatHistoryResponse> => request('/chat/history', { query, signal }),
  summarize: (sessionId: string, signal?: AbortSignal): Promise<SummarizeResponse> =>
    request('/chat/summarize', { method: 'POST', query: { session_id: sessionId }, signal }),
  clearMemory: (sessionId: string, signal?: AbortSignal): Promise<void> =>
    request('/chat/memory', { method: 'DELETE', query: { session_id: sessionId }, signal }),
} as const;
