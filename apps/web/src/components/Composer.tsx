import { useId, useState } from 'react';

import styles from './Composer.module.css';

interface ComposerProps {
  onSend: (message: string, options: { stream: boolean }) => void;
  onStop: () => void;
  isSending: boolean;
  disabled?: boolean;
}

const MAX_CHARS = 4000;
const HINT_THRESHOLD = Math.floor(MAX_CHARS * 0.8);

// The message composer. Enter sends; Shift+Enter inserts a newline. A "Stream
// responses" toggle switches between the SSE path (POST /chat/stream, tokens
// rendered live) and one synchronous round trip (POST /chat) — both share the
// same response schema. While a request is in flight the send control becomes a
// Stop control that aborts the stream. A character hint appears as the message
// approaches the backend's length cap.
export function Composer({
  onSend,
  onStop,
  isSending,
  disabled = false,
}: ComposerProps): React.JSX.Element {
  const [value, setValue] = useState('');
  const [stream, setStream] = useState(true);
  const textareaId = useId();
  const toggleId = useId();

  const canSend = value.trim() !== '' && !disabled && !isSending;
  const showCount = value.length >= HINT_THRESHOLD;

  const submit = (): void => {
    if (!canSend) {
      return;
    }
    onSend(value, { stream });
    setValue('');
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <form
      className={styles.composer}
      data-sending={isSending}
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <label className="sr-only" htmlFor={textareaId}>
        Message
      </label>
      <textarea
        id={textareaId}
        className={styles.input}
        value={value}
        maxLength={MAX_CHARS}
        onChange={(event) => {
          setValue(event.target.value);
        }}
        onKeyDown={handleKeyDown}
        placeholder="Ask about appointments, services, or your records…"
        rows={1}
        disabled={disabled}
      />
      <div className={styles.controls}>
        <label className={styles.toggle} htmlFor={toggleId}>
          <input
            id={toggleId}
            type="checkbox"
            checked={stream}
            onChange={(event) => {
              setStream(event.target.checked);
            }}
          />
          Stream responses
        </label>

        <div className={styles.right}>
          {showCount && (
            <span className={styles.count} data-limit={value.length >= MAX_CHARS}>
              {value.length}/{MAX_CHARS}
            </span>
          )}
          <span className={styles.hint} aria-hidden="true">
            Enter to send
          </span>
          {isSending ? (
            <button type="button" className={styles.stop} onClick={onStop}>
              <span className={styles.stopIcon} aria-hidden="true" />
              Stop
            </button>
          ) : (
            <button type="submit" className={styles.send} disabled={!canSend}>
              Send
              <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none">
                <path
                  d="M5 12h13M13 6l6 6-6 6"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          )}
        </div>
      </div>
    </form>
  );
}
