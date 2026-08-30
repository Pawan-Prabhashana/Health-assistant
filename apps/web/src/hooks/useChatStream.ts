// The chat send/stream controller for one active session.
//
// History is loaded once when a session opens (GET /chat/history); the turns a
// user sends during that session are tracked locally here and appended to the
// thread, so there is no mid-session refetch race and no duplicate rendering.
// Each send either streams over SSE (POST /chat/stream, tokens rendered
// incrementally) or, when streaming is turned off, runs one synchronous round
// trip (POST /chat). An AbortController makes an in-flight stream cancellable and
// aborts the previous one when a new message is sent.

import { useCallback, useEffect, useRef, useState } from 'react';

import { api } from '../api/client';
import { ApiError } from '../api/client';
import { streamChat } from '../api/sse';
import type { ChatResponse, Route, Verdict } from '../api/types';

export type TurnStatus = 'routing' | 'streaming' | 'done' | 'error';

export interface LocalTurn {
  id: string;
  userMessage: string;
  createdAt: string;
  route: Route | null;
  verdict: Verdict | null;
  answer: string;
  status: TurnStatus;
  stopped: boolean;
  result: ChatResponse | null;
  error: { code: string; message: string } | null;
}

export interface ChatStreamController {
  turns: LocalTurn[];
  isSending: boolean;
  send: (message: string, options?: { stream?: boolean }) => Promise<void>;
  cancel: () => void;
  reset: () => void;
}

function newId(): string {
  // A client-only id for keying local turns; not persisted.
  return `local-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function useChatStream(sessionId: string, phone: string | null): ChatStreamController {
  const [turns, setTurns] = useState<LocalTurn[]>([]);
  const [isSending, setIsSending] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);

  const patch = useCallback((id: string, update: Partial<LocalTurn>) => {
    setTurns((current) => current.map((turn) => (turn.id === id ? { ...turn, ...update } : turn)));
  }, []);

  const cancel = useCallback(() => {
    controllerRef.current?.abort();
  }, []);

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setTurns([]);
    setIsSending(false);
  }, []);

  // Abort any in-flight request when the hook unmounts (e.g. session switch).
  useEffect(
    () => () => {
      controllerRef.current?.abort();
    },
    [],
  );

  const send = useCallback(
    async (message: string, options?: { stream?: boolean }) => {
      const trimmed = message.trim();
      if (trimmed === '' || isSending) {
        return;
      }
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      const id = newId();
      const turn: LocalTurn = {
        id,
        userMessage: trimmed,
        createdAt: new Date().toISOString(),
        route: null,
        verdict: null,
        answer: '',
        status: 'routing',
        stopped: false,
        result: null,
        error: null,
      };
      setTurns((current) => [...current, turn]);
      setIsSending(true);

      const useStream = options?.stream ?? true;
      try {
        if (useStream) {
          await streamChat(
            { session_id: sessionId, message: trimmed, phone: phone ?? null },
            (event) => {
              switch (event.type) {
                case 'routing':
                  patch(id, { route: event.route, verdict: event.verdict });
                  break;
                case 'delta':
                  setTurns((current) =>
                    current.map((t) =>
                      t.id === id
                        ? { ...t, answer: t.answer + event.text, status: 'streaming' }
                        : t,
                    ),
                  );
                  break;
                case 'final':
                  patch(id, {
                    status: 'done',
                    result: event.data,
                    answer: event.data.answer,
                    route: (event.data.route as Route | null) ?? null,
                    verdict: event.data.verdict as Verdict,
                  });
                  break;
                case 'error':
                  patch(id, {
                    status: 'error',
                    error: { code: event.code, message: event.message },
                  });
                  break;
              }
            },
            controller.signal,
          );
        } else {
          const result = await api.chat(
            { session_id: sessionId, message: trimmed, phone: phone ?? null },
            controller.signal,
          );
          patch(id, {
            status: 'done',
            result,
            answer: result.answer,
            route: (result.route as Route | null) ?? null,
            verdict: result.verdict as Verdict,
          });
        }
      } catch (error) {
        if (controller.signal.aborted) {
          // User cancelled: keep whatever was generated, mark the turn stopped.
          patch(id, { status: 'done', stopped: true });
        } else {
          const message_ =
            error instanceof ApiError
              ? error.message
              : error instanceof Error
                ? error.message
                : 'The request failed.';
          const code = error instanceof ApiError ? error.code : 'network_error';
          patch(id, { status: 'error', error: { code, message: message_ } });
        }
      } finally {
        if (controllerRef.current === controller) {
          controllerRef.current = null;
          setIsSending(false);
        }
      }
    },
    [isSending, patch, phone, sessionId],
  );

  return { turns, isSending, send, cancel, reset };
}
