import { useEffect } from 'react';

import { ApiError } from './api/client';
import { AppProviders } from './app/AppProviders';
import { ChatPanel } from './components/ChatPanel';
import { HealthView } from './components/HealthView';
import { IdentityView } from './components/IdentityView';
import { SessionSidebar } from './components/SessionSidebar';
import { TopBar } from './components/TopBar';
import { usePatientByPhone } from './query/hooks';
import { useIdentity } from './state/identity';
import { useSessionState } from './state/session';
import styles from './App.module.css';

function ChatWorkspace({ phone }: { phone: string }): React.JSX.Element {
  const activeSessionId = useSessionState((state) => state.activeSessionId);
  const sidebarOpen = useSessionState((state) => state.sidebarOpen);
  const setSidebarOpen = useSessionState((state) => state.setSidebarOpen);

  return (
    <div className={styles.workspace}>
      <div className={styles.sidebarDock} data-open={sidebarOpen}>
        <SessionSidebar phone={phone} />
      </div>
      {sidebarOpen && (
        <button
          type="button"
          className={styles.overlay}
          aria-label="Close conversations"
          onClick={() => {
            setSidebarOpen(false);
          }}
        />
      )}
      <main className={styles.main}>
        {activeSessionId !== null ? (
          <ChatPanel key={activeSessionId} sessionId={activeSessionId} phone={phone} />
        ) : (
          <div className={styles.placeholder}>
            <div className={styles.placeholderInner}>
              <h2 className={styles.placeholderTitle}>Select a conversation</h2>
              <p className={styles.placeholderBody}>
                Choose a conversation, or start a new one to begin.
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function IdentifiedApp({ phone }: { phone: string }): React.JSX.Element {
  const patient = usePatientByPhone(phone);
  const clearIdentity = useIdentity((state) => state.clear);
  const view = useSessionState((state) => state.view);

  // If the stored phone no longer resolves (record erased elsewhere), sign out.
  useEffect(() => {
    if (patient.isError && patient.error instanceof ApiError && patient.error.status === 404) {
      clearIdentity();
    }
  }, [patient.isError, patient.error, clearIdentity]);

  return (
    <div className={styles.app}>
      <TopBar patient={patient.data ?? null} />
      {view === 'health' ? <HealthView /> : <ChatWorkspace phone={phone} />}
    </div>
  );
}

function Root(): React.JSX.Element {
  const phone = useIdentity((state) => state.phone);
  if (phone === null) {
    return <IdentityView />;
  }
  return <IdentifiedApp phone={phone} />;
}

export function App(): React.JSX.Element {
  return (
    <AppProviders>
      <Root />
    </AppProviders>
  );
}
