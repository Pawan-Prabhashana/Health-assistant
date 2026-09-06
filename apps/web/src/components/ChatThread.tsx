import { useEffect, useMemo, useRef } from 'react';

import type { ChatMessage } from '../api/types';
import { viewFromLocalTurn, viewFromMessage } from '../lib/assistant';
import { formatTime, routingMessage } from '../lib/format';
import type { LocalTurn } from '../hooks/useChatStream';
import { AssistantMessage } from './AssistantMessage';
import { Logo } from './Logo';
import styles from './ChatThread.module.css';

interface ChatThreadProps {
  history: ChatMessage[];
  turns: LocalTurn[];
}

function UserBubble({ content, time }: { content: string; time?: string }): React.JSX.Element {
  return (
    <div className={`${styles.row} ${styles.userRow}`}>
      <div className={styles.userBubble}>
        <p className={styles.userText}>{content}</p>
        {time !== undefined && time !== '' && <span className={styles.time}>{time}</span>}
      </div>
    </div>
  );
}

function AssistantRow({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <div className={`${styles.row} ${styles.assistantRow}`}>
      <span className={styles.avatar} aria-hidden="true">
        <Logo size={26} />
      </span>
      <div className={styles.assistantSlot}>{children}</div>
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
// through a polite live region. Autoscroll follows new content only while the
// user is near the bottom, so scrolling up to read is never yanked back.
export function ChatThread({ history, turns }: ChatThreadProps): React.JSX.Element {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);

  const announcement = useMemo(() => {
    const done = [...turns].reverse().find((turn) => turn.status === 'done' && turn.answer !== '');
    return done ? done.answer : '';
  }, [turns]);

  const handleScroll = (): void => {
    const el = scrollRef.current;
    if (el === null) {
      return;
    }
    pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 96;
  };

  useEffect(() => {
    const el = scrollRef.current;
    if (el !== null && pinnedRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [history, turns]);

  return (
    <div className={styles.thread} ref={scrollRef} onScroll={handleScroll}>
      <div className={styles.inner}>
        {history.map((message) =>
          message.role === 'user' ? (
            <UserBubble
              key={message.id}
              content={message.content}
              time={formatTime(message.created_at)}
            />
          ) : (
            <AssistantRow key={message.id}>
              <AssistantMessage view={viewFromMessage(message)} />
            </AssistantRow>
          ),
        )}

        {turns.map((turn) => (
          <div key={turn.id} className={styles.turn}>
            <UserBubble content={turn.userMessage} time={formatTime(turn.createdAt)} />
            {turn.status === 'routing' && turn.answer === '' ? (
              <AssistantRow>
                <RoutingIndicator route={turn.route} />
              </AssistantRow>
            ) : turn.status === 'error' ? (
              <AssistantRow>
                <div className={styles.error} role="alert">
                  <p className={styles.errorTitle}>Something went wrong</p>
                  <p className={styles.errorMessage}>{turn.error?.message}</p>
                </div>
              </AssistantRow>
            ) : (
              <AssistantRow>
                <AssistantMessage
                  view={viewFromLocalTurn(turn)}
                  streaming={turn.status === 'streaming'}
                />
              </AssistantRow>
            )}
          </div>
        ))}
      </div>

      <div className="sr-only" role="status" aria-live="polite">
        {announcement}
      </div>
    </div>
  );
}
