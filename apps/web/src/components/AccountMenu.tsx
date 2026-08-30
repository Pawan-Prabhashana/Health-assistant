import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import type { PatientResponse } from '../api/types';
import { useDeletePatient, usePatientById } from '../query/hooks';
import { useIdentity } from '../state/identity';
import { useSessionState } from '../state/session';
import styles from './AccountMenu.module.css';

interface AccountMenuProps {
  patient: PatientResponse;
}

// The identity chip and account panel. Shows who is signed in, lets the user
// fetch their authoritative record (GET /patients/{id}), sign out, and exercise
// PDPA erasure (DELETE /patients/{id}). Built on the native <details> element so
// it is keyboard-accessible without bespoke focus management.
export function AccountMenu({ patient }: AccountMenuProps): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const [confirmErase, setConfirmErase] = useState(false);
  const record = usePatientById(open ? patient.id : null);
  const deletePatient = useDeletePatient();
  const clearIdentity = useIdentity((state) => state.clear);
  const setActiveSession = useSessionState((state) => state.setActiveSession);
  const queryClient = useQueryClient();

  const signOut = (): void => {
    setActiveSession(null);
    clearIdentity();
    queryClient.clear();
  };

  const erase = (): void => {
    deletePatient.mutate(patient.id, {
      onSuccess: () => {
        signOut();
      },
    });
  };

  const shown = record.data ?? patient;

  return (
    <details
      className={styles.details}
      open={open}
      onToggle={(event) => {
        setOpen((event.target as HTMLDetailsElement).open);
      }}
    >
      <summary className={styles.summary}>
        <span className={styles.avatar} aria-hidden="true">
          {(patient.full_name || patient.phone).slice(0, 1).toUpperCase()}
        </span>
        <span className={styles.name}>{patient.full_name || patient.phone}</span>
      </summary>
      <div className={styles.panel} role="menu">
        <dl className={styles.record}>
          <div>
            <dt>Name</dt>
            <dd>{shown.full_name || '—'}</dd>
          </div>
          <div>
            <dt>Phone</dt>
            <dd>{shown.phone}</dd>
          </div>
          <div>
            <dt>Record</dt>
            <dd>{shown.mrn}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd className={styles.status} data-status={shown.status}>
              {shown.status}
            </dd>
          </div>
        </dl>

        <div className={styles.actions}>
          <button type="button" className="btn btn--ghost" onClick={signOut}>
            Sign out
          </button>
          {confirmErase ? (
            <button
              type="button"
              className="btn btn--danger"
              onClick={erase}
              disabled={deletePatient.isPending}
            >
              {deletePatient.isPending ? 'Erasing…' : 'Confirm erase'}
            </button>
          ) : (
            <button
              type="button"
              className="btn btn--danger"
              onClick={() => {
                setConfirmErase(true);
              }}
            >
              Erase my data
            </button>
          )}
        </div>
        {confirmErase && (
          <p className={styles.warning}>
            This permanently deletes your record and every conversation. This cannot be undone.
          </p>
        )}
      </div>
    </details>
  );
}
