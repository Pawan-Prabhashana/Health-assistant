import type { PatientResponse } from '../api/types';
import { useSessionState } from '../state/session';
import { AccountMenu } from './AccountMenu';
import { Logo } from './Logo';
import { ThemeToggle } from './ThemeToggle';
import styles from './TopBar.module.css';

interface TopBarProps {
  patient: PatientResponse | null;
}

// The application header: the brand, a menu button that opens the sidebar drawer
// on mobile, a segmented view switch (chat / status), the theme toggle, and the
// account menu when identified.
export function TopBar({ patient }: TopBarProps): React.JSX.Element {
  const view = useSessionState((state) => state.view);
  const setView = useSessionState((state) => state.setView);
  const sidebarOpen = useSessionState((state) => state.sidebarOpen);
  const setSidebarOpen = useSessionState((state) => state.setSidebarOpen);

  const showMenu = patient !== null && view === 'chat';

  return (
    <header className={styles.bar}>
      {showMenu && (
        <button
          type="button"
          className={styles.menu}
          aria-label="Open conversations"
          aria-expanded={sidebarOpen}
          onClick={() => {
            setSidebarOpen(!sidebarOpen);
          }}
        >
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none">
            <path
              d="M4 7h16M4 12h16M4 17h16"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
          </svg>
        </button>
      )}

      <div className={styles.brand}>
        <Logo size={28} />
        <span className={styles.wordmark}>Sahana</span>
      </div>

      {patient !== null && (
        <nav className={styles.nav} aria-label="Views">
          <button
            type="button"
            className={styles.tab}
            data-active={view === 'chat'}
            aria-current={view === 'chat' ? 'page' : undefined}
            onClick={() => {
              setView('chat');
            }}
          >
            Chat
          </button>
          <button
            type="button"
            className={styles.tab}
            data-active={view === 'health'}
            aria-current={view === 'health' ? 'page' : undefined}
            onClick={() => {
              setView('health');
            }}
          >
            Status
          </button>
        </nav>
      )}

      <div className={styles.right}>
        <ThemeToggle />
        {patient && <AccountMenu patient={patient} />}
      </div>
    </header>
  );
}
