import { citationSource } from '../lib/format';
import styles from './Citations.module.css';

interface CitationsProps {
  citations: string[];
}

function DocGlyph(): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true" fill="none">
      <path d="M7 3h7l4 4v14H7z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path
        d="M14 3v4h4M9.5 12h5M9.5 16h5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function WebGlyph(): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true" fill="none">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.6" />
      <path
        d="M3.5 12h17M12 3.5c2.5 2.4 2.5 14.6 0 17M12 3.5c-2.5 2.4-2.5 14.6 0 17"
        stroke="currentColor"
        strokeWidth="1.6"
      />
    </svg>
  );
}

// Renders RAG/web citations as elegant source chips: knowledge-base documents get
// a document glyph and title; web results get a globe glyph, the host as label,
// and a safe external link.
export function Citations({ citations }: CitationsProps): React.JSX.Element | null {
  if (citations.length === 0) {
    return null;
  }
  return (
    <div className={styles.wrap}>
      <p className={styles.heading}>Sources</p>
      <ul className={styles.chips}>
        {citations.map((citation, index) => {
          const source = citationSource(citation);
          return (
            <li key={`${citation}-${index}`}>
              {source.kind === 'web' && source.href !== null ? (
                <a
                  className={styles.chip}
                  data-kind="web"
                  href={source.href}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  <WebGlyph />
                  {source.label}
                </a>
              ) : (
                <span className={styles.chip} data-kind="kb">
                  <DocGlyph />
                  {source.label}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
