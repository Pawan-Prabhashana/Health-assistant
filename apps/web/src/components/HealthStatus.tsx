import { useEffect, useState } from 'react';

import { getReadiness, type ReadinessResponse } from '../api/health';

type State =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; data: ReadinessResponse };

/**
 * Fetches the backend readiness state on mount and renders the overall status
 * plus each registered dependency check. In Phase 0 the check list is empty,
 * which is the correct, healthy state.
 */
export function HealthStatus(): React.JSX.Element {
  const [state, setState] = useState<State>({ kind: 'loading' });

  useEffect(() => {
    const controller = new AbortController();

    getReadiness(controller.signal)
      .then((data) => {
        setState({ kind: 'ready', data });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        const message = error instanceof Error ? error.message : 'Unknown error';
        setState({ kind: 'error', message });
      });

    return () => {
      controller.abort();
    };
  }, []);

  if (state.kind === 'loading') {
    return <p className="health-status health-status--loading">Checking backend readiness…</p>;
  }

  if (state.kind === 'error') {
    return (
      <div className="health-status health-status--error" role="alert">
        <p>Could not reach the API.</p>
        <p className="health-status__detail">{state.message}</p>
      </div>
    );
  }

  const { ready, checks } = state.data;

  return (
    <section className="health-status" aria-live="polite">
      <p className={`health-status__badge ${ready ? 'is-ready' : 'is-not-ready'}`}>
        {ready ? 'Ready' : 'Not ready'}
      </p>
      {checks.length === 0 ? (
        <p className="health-status__empty">No dependency checks registered.</p>
      ) : (
        <ul className="health-status__checks">
          {checks.map((check) => (
            <li key={check.name} className={check.ok ? 'is-ok' : 'is-failing'}>
              <span className="health-status__name">{check.name}</span>
              <span className="health-status__state">{check.ok ? 'ok' : 'failing'}</span>
              {check.detail !== null && (
                <span className="health-status__detail">{check.detail}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
