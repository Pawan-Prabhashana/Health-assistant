import { useEffect, useMemo, useRef } from 'react';

import type { ChatMessage } from '../api/types';
import { viewFromLocalTurn, viewFromMessage } from '../lib/assistant';
import { formatTime, routingMessage } from '../lib/format';
import type { LocalTurn } from '../hooks/useChatStream';
import { AssistantMessage } from './AssistantMessage';
import styles from './ChatThread.module.css';

interface ChatThreadProps {
  history: ChatMessage[];
  turns: LocalTurn[];
}

function UserBubble({ content, time }: { content: string; time?: string }): React.JSX.Element {
  return (
    <div className={styles.userRow}>
      <div className={styles.userBubble}>
        <p className={styles.userText}>{content}</p>
        {time !== undefined && time !== '' && <span className={styles.time}>{time}</span>}
      </div>
    </div>
  );
}

function RoutingIndicator({ route }: { route: LocalTurn['route'] }): React.JSX.Element {
  return (
    <div className={styles.routing} aria-hidden="true">
      <span className={styles.dots}>
        <span />
        <span />
        <span />
      </span>
      <span className={styles.routingText}>{routingMessage(route)}</span>
    </div>
  );
}

// The message list for the active session: persisted history first, then the
// turns sent in this session. Deltas render incrementally into the assistant
// bubble; the completed answer (not each token) is announced to screen readers
// through a polite live region so the stream is not read out character by
// character.
export function ChatThread({ history, turns }: ChatThreadProps): React.JSX.Element {
  const bottomRef = useRef<HTMLDivElement>(null);

  const announcement = useMemo(() => {
    const done = [...turns].reverse().find((turn) => turn.status === 'done' && turn.answer !== '');
    return done ? done.answer : '';
  }, [turns]);

  useEffect(() => {
    // `scrollIntoView` is unavailable in the jsdom test environment.
    if (typeof bottomRef.current?.scrollIntoView === 'function') {
      bottomRef.current.scrollIntoView({ block: 'end' });
    }
  }, [history, turns]);

  return (
    <div className={styles.thread}>
      {history.map((message) =>
        message.role === 'user' ? (
          <UserBubble
            key={message.id}
            content={message.content}
            time={formatTime(message.created_at)}
          />
        ) : (
          <AssistantMessage key={message.id} view={viewFromMessage(message)} />
        ),
      )}

      {turns.map((turn) => (
        <div key={turn.id} className={styles.turn}>
          <UserBubble content={turn.userMessage} time={formatTime(turn.createdAt)} />
          {turn.status === 'routing' && turn.answer === '' ? (
            <RoutingIndicator route={turn.route} />
          ) : turn.status === 'error' ? (
            <div className={styles.error} role="alert">
              <p className={styles.errorTitle}>Something went wrong</p>
              <p className={styles.errorMessage}>{turn.error?.message}</p>
            </div>
          ) : (
            <AssistantMessage
              view={viewFromLocalTurn(turn)}
              streaming={turn.status === 'streaming'}
            />
          )}
        </div>
      ))}

      <div className="sr-only" role="status" aria-live="polite">
        {announcement}
      </div>
      <div ref={bottomRef} />
    </div>
  );
}
