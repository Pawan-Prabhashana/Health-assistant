import { useConfig, useLiveness, useReadiness } from '../query/hooks';
import styles from './HealthView.module.css';

// The operational status view: liveness, aggregate readiness with each
// dependency check, and the non-secret runtime config. Everything is read
// through the typed client, so it also proves the browser → nginx → api path.
export function HealthView(): React.JSX.Element {
  const liveness = useLiveness();
  const readiness = useReadiness();
  const config = useConfig();

  return (
    <main className={styles.view}>
      <div className={styles.inner}>
        <h1 className={styles.title}>System status</h1>
        <p className={styles.lede}>Live readiness reported by the API through the proxy.</p>

        <section className={styles.card} aria-labelledby="overall-heading">
          <h2 id="overall-heading" className={styles.cardTitle}>
            Overall
          </h2>
          <div className={styles.badges}>
            <span
              className={styles.badge}
              data-tone={liveness.data ? 'ok' : liveness.isError ? 'fail' : 'idle'}
            >
              {liveness.isLoading ? 'Live: checking…' : liveness.data ? 'Live' : 'Not live'}
            </span>
            <span
              className={styles.badge}
              data-tone={readiness.data?.ready ? 'ok' : readiness.isLoading ? 'idle' : 'fail'}
            >
              {readiness.isLoading
                ? 'Ready: checking…'
                : readiness.data?.ready
                  ? 'Ready'
                  : 'Not ready'}
            </span>
          </div>
        </section>

        <section className={styles.card} aria-labelledby="checks-heading" aria-live="polite">
          <h2 id="checks-heading" className={styles.cardTitle}>
            Dependency checks
          </h2>
          {readiness.isLoading ? (
            <p className={styles.muted}>Loading checks…</p>
          ) : readiness.isError ? (
            <p className={styles.muted} role="alert">
              Could not reach the API.
            </p>
          ) : (readiness.data?.checks?.length ?? 0) === 0 ? (
            <p className={styles.muted}>No dependency checks registered.</p>
          ) : (
            <ul className={styles.checks}>
              {(readiness.data?.checks ?? []).map((check) => (
                <li key={check.name} className={styles.check} data-ok={check.ok}>
                  <span className={styles.checkName}>{check.name}</span>
                  <span className={styles.checkState}>{check.ok ? 'ok' : 'failing'}</span>
                  {check.detail !== null && check.detail !== undefined && (
                    <span className={styles.checkDetail}>{check.detail}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        {config.data && (
          <section className={styles.card} aria-labelledby="config-heading">
            <h2 id="config-heading" className={styles.cardTitle}>
              Runtime
            </h2>
            <dl className={styles.config}>
              <div>
                <dt>Environment</dt>
                <dd>{config.data.app_env}</dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd>{config.data.version}</dd>
              </div>
              <div>
                <dt>Log level</dt>
                <dd>{config.data.log_level}</dd>
              </div>
            </dl>
            {Object.keys(config.data.features ?? {}).length > 0 && (
              <ul className={styles.features}>
                {Object.entries(config.data.features ?? {}).map(([name, enabled]) => (
                  <li key={name} data-on={enabled}>
                    {name}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </div>
    </main>
  );
}
