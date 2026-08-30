import { useId, useState } from 'react';

import { isPlausiblePhone } from '../lib/phone';
import { useUpsertPatient } from '../query/hooks';
import { useIdentity } from '../state/identity';
import styles from './IdentityView.module.css';

// The identify screen: the user enters a phone number, which upserts a patient
// (POST /patients) and holds the phone as the app identity, persisted across
// reloads. The phone is validated client-side before sending; the backend
// normalises to E.164 and is the final authority.
export function IdentityView(): React.JSX.Element {
  const [phone, setPhone] = useState('');
  const [name, setName] = useState('');
  const [touched, setTouched] = useState(false);
  const upsert = useUpsertPatient();
  const setIdentityPhone = useIdentity((state) => state.setPhone);
  const phoneId = useId();
  const nameId = useId();

  const valid = isPlausiblePhone(phone);

  const handleSubmit = (event: React.FormEvent): void => {
    event.preventDefault();
    setTouched(true);
    if (!valid) {
      return;
    }
    upsert.mutate(
      { phone: phone.trim(), ...(name.trim() !== '' ? { fullName: name.trim() } : {}) },
      {
        onSuccess: (patient) => {
          setIdentityPhone(patient.phone);
        },
      },
    );
  };

  const showValidationError = touched && !valid;
  const serverError = upsert.isError ? upsert.error.message : null;

  return (
    <main className={styles.wrap}>
      <section className={styles.card}>
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true">
            S
          </span>
          <div>
            <h1 className={styles.title}>Sahana</h1>
            <p className={styles.tagline}>Hospital health assistant</p>
          </div>
        </div>

        <p className={styles.intro}>
          Enter your phone number to continue. We use it to find your record and keep your
          conversations together.
        </p>

        <form className={styles.form} onSubmit={handleSubmit} noValidate>
          <div>
            <label className="field-label" htmlFor={phoneId}>
              Phone number
            </label>
            <input
              id={phoneId}
              className="text-input"
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              value={phone}
              onChange={(event) => {
                setPhone(event.target.value);
              }}
              onBlur={() => {
                setTouched(true);
              }}
              placeholder="e.g. 077 123 4567"
              aria-invalid={showValidationError}
              aria-describedby={showValidationError ? `${phoneId}-error` : undefined}
            />
            {showValidationError && (
              <p id={`${phoneId}-error`} className={styles.error} role="alert">
                Enter a valid phone number.
              </p>
            )}
          </div>

          <div>
            <label className="field-label" htmlFor={nameId}>
              Name <span className={styles.optional}>(optional)</span>
            </label>
            <input
              id={nameId}
              className="text-input"
              type="text"
              autoComplete="name"
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
              placeholder="How should we address you?"
            />
          </div>

          {serverError !== null && (
            <p className={styles.error} role="alert">
              {serverError}
            </p>
          )}

          <button type="submit" className="btn btn--primary" disabled={upsert.isPending}>
            {upsert.isPending ? 'Continuing…' : 'Continue'}
          </button>
        </form>

        <p className={styles.privacy}>
          Only your phone number is stored in this browser. It is never shared beyond this app.
        </p>
      </section>
    </main>
  );
}
