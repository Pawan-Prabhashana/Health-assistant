import { formatRelative } from '../lib/format';
import { useCreateSession, useDeleteSession, useSessions } from '../query/hooks';
import { useSessionState } from '../state/session';
import styles from './SessionSidebar.module.css';

interface SessionSidebarProps {
  phone: string;
}

function SkeletonList(): React.JSX.Element {
  return (
    <ul className={styles.list} aria-hidden="true">
      {[0, 1, 2, 3].map((index) => (
        <li key={index} className={styles.skeletonRow}>
          <span className={`skeleton ${styles.skeletonTitle}`} />
          <span className={`skeleton ${styles.skeletonMeta}`} />
        </li>
      ))}
    </ul>
  );
}

// The conversation list for the identified patient: create, select, and delete
// threads, with designed loading (skeletons), empty, and error states. On mobile
// the parent renders this inside a drawer; selecting or creating closes it.
export function SessionSidebar({ phone }: SessionSidebarProps): React.JSX.Element {
  const sessions = useSessions(phone);
  const createSession = useCreateSession(phone);
  const deleteSession = useDeleteSession(phone);
  const activeSessionId = useSessionState((state) => state.activeSessionId);
  const setActiveSession = useSessionState((state) => state.setActiveSession);
  const setSidebarOpen = useSessionState((state) => state.setSidebarOpen);

  const handleCreate = (): void => {
    createSession.mutate(
      {},
      {
        onSuccess: (session) => {
          setActiveSession(session.id);
          setSidebarOpen(false);
        },
      },
    );
  };

  const handleSelect = (sessionId: string): void => {
    setActiveSession(sessionId);
    setSidebarOpen(false);
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
          className={styles.newButton}
          onClick={handleCreate}
          disabled={createSession.isPending}
        >
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none">
            <path
              d="M12 5v14M5 12h14"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
          {createSession.isPending ? 'Creating…' : 'New'}
        </button>
      </div>

      {sessions.isLoading ? (
        <SkeletonList />
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
        <div className={styles.empty}>
          <p className={styles.emptyText}>No conversations yet. Start a new one.</p>
        </div>
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
                    handleSelect(session.id);
                  }}
                >
                  <span className={styles.itemTitle}>{session.title}</span>
                  <span className={styles.itemDate}>{formatRelative(session.updated_at)}</span>
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
                  <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" fill="none">
                    <path
                      d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13"
                      stroke="currentColor"
                      strokeWidth="1.7"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </nav>
  );
}
