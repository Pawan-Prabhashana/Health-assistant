import { useId, useState } from 'react';

import { isPlausiblePhone } from '../lib/phone';
import { useUpsertPatient } from '../query/hooks';
import { useIdentity } from '../state/identity';
import { Logo } from './Logo';
import { ThemeToggle } from './ThemeToggle';
import styles from './IdentityView.module.css';

const HIGHLIGHTS = [
  'Answers grounded in the hospital knowledge base',
  'Your appointments and record, only for you',
  'Private by design — nothing shared beyond this app',
];

// The identify screen: a calm "front desk". The user enters a phone number,
// which upserts a patient (POST /patients) and holds the phone as the app
// identity, persisted across reloads. The phone is validated client-side before
// sending; the backend normalises to E.164 and is the final authority.
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
      <div className={styles.themeCorner}>
        <ThemeToggle />
      </div>

      <div className={styles.grid}>
        <section className={styles.pitch}>
          <Logo size={44} />
          <h1 className={styles.title}>Sahana</h1>
          <p className={styles.lede}>
            A calm, trustworthy assistant for hospital services — appointments, guidance, and your
            record, in one place.
          </p>
          <ul className={styles.highlights}>
            {HIGHLIGHTS.map((item) => (
              <li key={item} className={styles.highlight}>
                <span className={styles.check} aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none">
                    <path
                      d="M5 12.5l4 4 10-10"
                      stroke="currentColor"
                      strokeWidth="2.2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
                {item}
              </li>
            ))}
          </ul>
        </section>

        <section className={styles.card} aria-label="Sign in">
          <h2 className={styles.cardTitle}>Welcome</h2>
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

            <button
              type="submit"
              className={`btn btn--primary ${styles.submit}`}
              disabled={upsert.isPending}
            >
              {upsert.isPending ? 'Continuing…' : 'Continue'}
            </button>
          </form>

          <p className={styles.privacy}>
            <span className={styles.lock} aria-hidden="true">
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none">
                <rect
                  x="5"
                  y="11"
                  width="14"
                  height="9"
                  rx="2"
                  stroke="currentColor"
                  strokeWidth="1.7"
                />
                <path d="M8 11V8a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="1.7" />
              </svg>
            </span>
            Only your phone number is stored in this browser. It is never shared beyond this app.
          </p>
        </section>
      </div>
    </main>
  );
}
