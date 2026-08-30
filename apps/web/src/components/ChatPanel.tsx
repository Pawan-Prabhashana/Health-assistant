import { useState } from 'react';

import { useChatStream } from '../hooks/useChatStream';
import { useClearMemory, useHistory, useSession, useSummarize } from '../query/hooks';
import { ChatThread } from './ChatThread';
import { Composer } from './Composer';
import styles from './ChatPanel.module.css';

interface ChatPanelProps {
  sessionId: string;
  phone: string | null;
}

const EXAMPLES = [
  'What are your visiting hours?',
  'What is the status of my record?',
  'Do you have a pharmacy on site?',
];

// The active-session view: header with memory actions, the message thread
// (history + live turns), and the composer. Mounted with a `key` of the session
// id by the shell, so switching sessions resets all in-flight state cleanly.
export function ChatPanel({ sessionId, phone }: ChatPanelProps): React.JSX.Element {
  const history = useHistory(sessionId);
  const session = useSession(sessionId);
  const summarize = useSummarize();
  const clearMemory = useClearMemory();
  const chat = useChatStream(sessionId, phone);
  const [notice, setNotice] = useState<string | null>(null);

  const handleSummarize = (): void => {
    setNotice(null);
    summarize.mutate(sessionId, {
      onSuccess: (result) => {
        setNotice(result.updated ? 'Conversation summarised.' : 'Nothing new to summarise yet.');
      },
      onError: () => {
        setNotice('Could not refresh the summary.');
      },
    });
  };

  const handleClearMemory = (): void => {
    setNotice(null);
    clearMemory.mutate(sessionId, {
      onSuccess: () => {
        chat.reset();
        setNotice('Short-term memory cleared.');
      },
      onError: () => {
        setNotice('Could not clear memory.');
      },
    });
  };

  const messages = history.data?.messages ?? [];
  const isEmpty = messages.length === 0 && chat.turns.length === 0;

  return (
    <section className={styles.panel} aria-label="Conversation">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <h2 className={styles.title}>{session.data?.title ?? 'Conversation'}</h2>
          <p className={styles.subtitle}>
            {history.data ? `${history.data.total} messages` : 'Loading…'}
          </p>
        </div>
        <div className={styles.actions}>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={handleSummarize}
            disabled={summarize.isPending}
          >
            {summarize.isPending ? 'Summarising…' : 'Summarise'}
          </button>
          <button
            type="button"
            className="btn btn--danger"
            onClick={handleClearMemory}
            disabled={clearMemory.isPending}
          >
            Clear memory
          </button>
        </div>
      </header>

      {notice !== null && (
        <p className={styles.notice} role="status">
          {notice}
        </p>
      )}

      <div className={styles.scroll}>
        {history.isLoading ? (
          <p className={styles.state}>Loading conversation…</p>
        ) : history.isError ? (
          <div className={styles.state} role="alert">
            <p>Could not load this conversation.</p>
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => {
                void history.refetch();
              }}
            >
              Retry
            </button>
          </div>
        ) : isEmpty ? (
          <div className={styles.empty}>
            <h3 className={styles.emptyTitle}>How can I help?</h3>
            <p className={styles.emptyBody}>
              Ask about hospital services, your appointments, or general questions. Try one of
              these:
            </p>
            <ul className={styles.examples}>
              {EXAMPLES.map((example) => (
                <li key={example}>
                  <button
                    type="button"
                    className={styles.example}
                    onClick={() => {
                      void chat.send(example, { stream: true });
                    }}
                  >
                    {example}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <ChatThread history={messages} turns={chat.turns} />
        )}
      </div>

      <div className={styles.composerWrap}>
        <Composer
          onSend={(message, options) => {
            void chat.send(message, options);
          }}
          onStop={chat.cancel}
          isSending={chat.isSending}
        />
      </div>
    </section>
  );
}
