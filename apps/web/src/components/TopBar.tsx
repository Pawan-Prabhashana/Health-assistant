import type { PatientResponse } from '../api/types';
import { useSessionState } from '../state/session';
import { AccountMenu } from './AccountMenu';
import styles from './TopBar.module.css';

interface TopBarProps {
  patient: PatientResponse | null;
}

// The application header: brand, a toggle between the chat and health/status
// views, and the account menu when identified.
export function TopBar({ patient }: TopBarProps): React.JSX.Element {
  const view = useSessionState((state) => state.view);
  const setView = useSessionState((state) => state.setView);

  return (
    <header className={styles.bar}>
      <div className={styles.brand}>
        <span className={styles.mark} aria-hidden="true">
          S
        </span>
        <span className={styles.wordmark}>Sahana</span>
      </div>

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

      <div className={styles.right}>{patient && <AccountMenu patient={patient} />}</div>
    </header>
  );
}
