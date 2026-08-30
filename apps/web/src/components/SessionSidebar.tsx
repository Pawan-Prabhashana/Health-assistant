import { useCreateSession, useDeleteSession, useSessions } from '../query/hooks';
import { useSessionState } from '../state/session';
import styles from './SessionSidebar.module.css';

interface SessionSidebarProps {
  phone: string;
}

// The conversation list for the identified patient: create, select, and delete
// threads. Loading, empty, and error states are all rendered explicitly rather
// than left blank.
export function SessionSidebar({ phone }: SessionSidebarProps): React.JSX.Element {
  const sessions = useSessions(phone);
  const createSession = useCreateSession(phone);
  const deleteSession = useDeleteSession(phone);
  const activeSessionId = useSessionState((state) => state.activeSessionId);
  const setActiveSession = useSessionState((state) => state.setActiveSession);

  const handleCreate = (): void => {
    createSession.mutate(
      {},
      {
        onSuccess: (session) => {
          setActiveSession(session.id);
        },
      },
    );
  };

  const handleDelete = (sessionId: string): void => {
    deleteSession.mutate(sessionId, {
      onSuccess: () => {
        if (activeSessionId === sessionId) {
          setActiveSession(null);
        }
      },
    });
  };

  return (
    <nav className={styles.sidebar} aria-label="Conversations">
      <div className={styles.head}>
        <h2 className={styles.heading}>Conversations</h2>
        <button
          type="button"
          className="btn btn--primary"
          onClick={handleCreate}
          disabled={createSession.isPending}
        >
          {createSession.isPending ? 'Creating…' : 'New'}
        </button>
      </div>

      {sessions.isLoading ? (
        <p className={styles.state}>Loading conversations…</p>
      ) : sessions.isError ? (
        <div className={styles.state} role="alert">
          <p>Could not load conversations.</p>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => {
              void sessions.refetch();
            }}
          >
            Retry
          </button>
        </div>
      ) : (sessions.data?.length ?? 0) === 0 ? (
        <p className={styles.state}>No conversations yet. Start a new one.</p>
      ) : (
        <ul className={styles.list}>
          {sessions.data?.map((session) => {
            const isActive = session.id === activeSessionId;
            return (
              <li key={session.id} className={styles.item}>
                <button
                  type="button"
                  className={styles.select}
                  data-active={isActive}
                  aria-current={isActive ? 'true' : undefined}
                  onClick={() => {
                    setActiveSession(session.id);
                  }}
                >
                  <span className={styles.itemTitle}>{session.title}</span>
                  <span className={styles.itemDate}>
                    {new Date(session.updated_at).toLocaleDateString()}
                  </span>
                </button>
                <button
                  type="button"
                  className={styles.delete}
                  aria-label={`Delete ${session.title}`}
                  onClick={() => {
                    handleDelete(session.id);
                  }}
                  disabled={deleteSession.isPending}
                >
                  <span aria-hidden="true">×</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </nav>
  );
}
