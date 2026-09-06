import type { TableResponse } from '../api/types';
import styles from './CrmTable.module.css';

interface CrmTableProps {
  table: TableResponse;
}

// Renders the CRM structured payload as a clinical data card — a titled record
// panel wrapping a real, accessible table (columns come from the backend:
// Patient ID, Name, Status, Next Appt). The status cell carries a data attribute
// so a clinical status reads with an appropriate tone.
export function CrmTable({ table }: CrmTableProps): React.JSX.Element {
  const statusIndex = table.columns.findIndex((column) => column.toLowerCase() === 'status');
  return (
    <div className={styles.card} role="region" aria-label="Your record">
      <div className={styles.header}>
        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none">
          <rect x="5" y="4" width="14" height="17" rx="2" stroke="currentColor" strokeWidth="1.7" />
          <path
            d="M9 4.5h6V7H9zM8.5 12h7M8.5 16h4"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
          />
        </svg>
        <span className={styles.headerTitle}>Your record</span>
      </div>
      <div className={styles.scroll}>
        <table className={styles.table}>
          <caption className="sr-only">Your patient record</caption>
          <thead>
            <tr>
              {table.columns.map((column) => (
                <th key={column} scope="col">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => {
                  const isStatus = cellIndex === statusIndex;
                  return (
                    <td
                      key={cellIndex}
                      {...(isStatus ? { 'data-status': cell.toLowerCase() } : {})}
                    >
                      {isStatus ? <span className={styles.status}>{cell}</span> : cell}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
