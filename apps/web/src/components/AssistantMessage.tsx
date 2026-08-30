import { answerKind, formatLatency } from '../lib/format';
import type { AssistantView } from '../lib/assistant';
import { Citations } from './Citations';
import { CrmTable } from './CrmTable';
import { RouteBadge } from './RouteBadge';
import styles from './AssistantMessage.module.css';

interface AssistantMessageProps {
  view: AssistantView;
  /** True while tokens are still streaming into this turn. */
  streaming?: boolean;
}

// Renders a completed (or streaming) assistant turn. The visual treatment is
// driven by the answer kind: a refusal reads as a calm boundary, a cache hit
// carries a quiet "answered instantly" affordance, and a tool-backed answer
// shows its CRM table, citations, route, and latency.
export function AssistantMessage({
  view,
  streaming = false,
}: AssistantMessageProps): React.JSX.Element {
  const kind = view.verdict ? answerKind(view.verdict) : 'answer';
  const showMeta = !streaming && (view.route !== null || view.latencyMs !== null || view.cached);

  return (
    <div className={styles.message} data-kind={kind}>
      <div className={styles.body}>
        {kind === 'refusal' && <p className={styles.boundaryLabel}>Outside what I can help with</p>}
        <p className={styles.answer}>
          {view.answer}
          {streaming && <span className={styles.caret} aria-hidden="true" />}
        </p>
        {view.structured && <CrmTable table={view.structured} />}
        <Citations citations={view.citations} />
        {view.incomplete && <p className={styles.incomplete}>Response stopped.</p>}
      </div>

      {showMeta && (
        <div className={styles.meta}>
          <RouteBadge route={view.route} cached={view.cached} />
          {view.latencyMs !== null && (
            <span className={styles.metaText}>{formatLatency(view.latencyMs)}</span>
          )}
          {view.totalTokens !== null && (
            <span className={styles.metaText}>{view.totalTokens} tokens</span>
          )}
        </div>
      )}
    </div>
  );
}
