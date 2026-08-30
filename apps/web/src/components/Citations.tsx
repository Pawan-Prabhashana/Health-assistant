import styles from './Citations.module.css';

interface CitationsProps {
  citations: string[];
}

function isUrl(value: string): boolean {
  return /^https?:\/\//i.test(value);
}

// Renders RAG/web citations as a compact, labelled source list. URL citations
// (web search) become safe external links; knowledge-base citations render as
// plain source labels.
export function Citations({ citations }: CitationsProps): React.JSX.Element | null {
  if (citations.length === 0) {
    return null;
  }
  return (
    <div className={styles.wrap}>
      <p className={styles.heading}>Sources</p>
      <ol className={styles.list}>
        {citations.map((citation, index) => (
          <li key={`${citation}-${index}`} className={styles.item}>
            {isUrl(citation) ? (
              <a href={citation} target="_blank" rel="noreferrer noopener">
                {citation}
              </a>
            ) : (
              <span>{citation}</span>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
