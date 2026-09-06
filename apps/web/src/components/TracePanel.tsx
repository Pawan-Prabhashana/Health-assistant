import type { TraceEntry } from '../api/types';
import styles from './TracePanel.module.css';

interface TracePanelProps {
  trace: TraceEntry[];
}

// An off-by-default disclosure surfacing the PII-free reasoning trace for a turn
// — the parallel classifiers' decision, the chosen route, and timings. Excellent
// for demos and for showing the architecture without cluttering the answer. Built
// on the native <details> element, so it is keyboard-accessible for free.
export function TracePanel({ trace }: TracePanelProps): React.JSX.Element {
  return (
    <details className={styles.trace}>
      <summary className={styles.summary}>Reasoning trace</summary>
      <ol className={styles.list}>
        {trace.map((entry, index) => (
          <li key={`${entry.node}-${index}`} className={styles.entry}>
            <span className={styles.node}>{entry.node}</span>
            {Object.keys(entry.data).length > 0 && (
              <span className={styles.data}>
                {Object.entries(entry.data).map(([key, value]) => (
                  <span key={key} className={styles.pair}>
                    <span className={styles.key}>{key}</span>
                    {String(value)}
                  </span>
                ))}
              </span>
            )}
          </li>
        ))}
      </ol>
    </details>
  );
}
