import { useId, useState } from 'react';

import styles from './Composer.module.css';

interface ComposerProps {
  onSend: (message: string, options: { stream: boolean }) => void;
  onStop: () => void;
  isSending: boolean;
  disabled?: boolean;
}

// The message composer. Enter sends; Shift+Enter inserts a newline. A "Stream
// responses" toggle switches between the SSE path (POST /chat/stream, tokens
// rendered live) and one synchronous round trip (POST /chat) — both share the
// same response schema. While a request is in flight the send control becomes a
// Stop control that aborts the stream.
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
        onChange={(event) => {
          setValue(event.target.value);
        }}
        onKeyDown={handleKeyDown}
        placeholder="Ask about appointments, services, or your records…"
        rows={2}
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
        {isSending ? (
          <button type="button" className="btn btn--ghost" onClick={onStop}>
            Stop
          </button>
        ) : (
          <button type="submit" className="btn btn--primary" disabled={!canSend}>
            Send
          </button>
        )}
      </div>
    </form>
  );
}
