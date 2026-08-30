import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { TableResponse } from '../api/types';
import { CrmTable } from './CrmTable';

const table: TableResponse = {
  columns: ['Patient ID', 'Name', 'Status', 'Next Appt'],
  rows: [['P-10023', 'Test Patient', 'stable', '12 Sep 2026, 10:30']],
};

describe('CrmTable', () => {
  it('renders the CRM payload as an accessible table with headers and a row', () => {
    render(<CrmTable table={table} />);
    const grid = screen.getByRole('table');
    for (const column of table.columns) {
      expect(within(grid).getByRole('columnheader', { name: column })).toBeInTheDocument();
    }
    expect(within(grid).getByRole('cell', { name: 'P-10023' })).toBeInTheDocument();
    expect(within(grid).getByRole('cell', { name: 'Test Patient' })).toBeInTheDocument();
    expect(within(grid).getByText('stable')).toBeInTheDocument();
    expect(within(grid).getByRole('cell', { name: '12 Sep 2026, 10:30' })).toBeInTheDocument();
  });
});
