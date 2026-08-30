import type { TableResponse } from '../api/types';
import styles from './CrmTable.module.css';

interface CrmTableProps {
  table: TableResponse;
}

// Renders the CRM structured payload as a real, accessible table (the columns
// come from the backend: Patient ID, Name, Status, Next Appt). The status cell
// carries a data attribute so a clinical status reads with an appropriate tone.
export function CrmTable({ table }: CrmTableProps): React.JSX.Element {
  const statusIndex = table.columns.findIndex((column) => column.toLowerCase() === 'status');
  return (
    <div className={styles.wrap} role="region" aria-label="Your record">
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
                  <td key={cellIndex} {...(isStatus ? { 'data-status': cell.toLowerCase() } : {})}>
                    {isStatus ? <span className={styles.status}>{cell}</span> : cell}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
