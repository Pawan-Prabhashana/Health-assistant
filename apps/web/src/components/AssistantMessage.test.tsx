import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { AssistantView } from '../lib/assistant';
import { AssistantMessage } from './AssistantMessage';

function view(overrides: Partial<AssistantView> = {}): AssistantView {
  return {
    answer: 'An answer.',
    verdict: 'proceed',
    route: 'rag',
    citations: [],
    structured: null,
    latencyMs: 1700,
    cached: false,
    incomplete: false,
    totalTokens: null,
    ...overrides,
  };
}

describe('AssistantMessage', () => {
  it('renders a refusal as a calm boundary', () => {
    render(
      <AssistantMessage
        view={view({ verdict: 'out_of_scope', route: null, answer: 'I can only help with…' })}
      />,
    );
    expect(screen.getByText('Outside what I can help with')).toBeInTheDocument();
    expect(screen.getByText('I can only help with…')).toBeInTheDocument();
    expect(screen.getByText('Refusal')).toBeInTheDocument();
  });

  it('shows an "answered instantly" affordance for a cache hit', () => {
    render(<AssistantMessage view={view({ cached: true, verdict: 'cache_hit' })} />);
    expect(screen.getByText('Answered instantly')).toBeInTheDocument();
  });

  it('renders citations and the route/latency for a tool-backed answer', () => {
    render(<AssistantMessage view={view({ citations: ['Visiting Hours'] })} />);
    expect(screen.getByText('Knowledge base')).toBeInTheDocument();
    expect(screen.getByText('1.7 s')).toBeInTheDocument();
    expect(screen.getByText('Visiting Hours')).toBeInTheDocument();
  });

  it('renders the CRM table when structured data is present', () => {
    render(
      <AssistantMessage
        view={view({
          route: 'crm',
          structured: { columns: ['Patient ID', 'Status'], rows: [['P-10023', 'stable']] },
        })}
      />,
    );
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByText('Your records')).toBeInTheDocument();
  });
});
