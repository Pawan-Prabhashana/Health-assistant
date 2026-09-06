import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { LocalTurn } from '../hooks/useChatStream';
import { makeChatResponse } from '../test/fixtures';
import { ChatThread } from './ChatThread';

function turn(overrides: Partial<LocalTurn>): LocalTurn {
  return {
    id: 'local-1',
    userMessage: 'Do I have an appointment today?',
    createdAt: '2026-09-01T10:00:00Z',
    route: null,
    verdict: null,
    answer: '',
    status: 'routing',
    stopped: false,
    result: null,
    error: null,
    ...overrides,
  };
}

describe('ChatThread streaming affordance', () => {
  it('shows the route-specific thinking indicator while routing', () => {
    render(<ChatThread history={[]} turns={[turn({ route: 'crm', status: 'routing' })]} />);
    expect(screen.getByText('Checking your records…')).toBeInTheDocument();
  });

  it('renders partial tokens while streaming', () => {
    render(
      <ChatThread
        history={[]}
        turns={[turn({ route: 'rag', status: 'streaming', answer: 'Our visiting' })]}
      />,
    );
    expect(screen.getByText('Our visiting')).toBeInTheDocument();
  });

  it('resolves to the final answer with its route badge', () => {
    const result = makeChatResponse({ route: 'rag', answer: 'Visiting hours are 10am to 8pm.' });
    render(
      <ChatThread
        history={[]}
        turns={[
          turn({
            route: 'rag',
            verdict: 'proceed',
            status: 'done',
            answer: 'Visiting hours are 10am to 8pm.',
            result,
          }),
        ]}
      />,
    );
    // The answer appears in the bubble and in the polite live region.
    expect(screen.getAllByText('Visiting hours are 10am to 8pm.').length).toBeGreaterThan(0);
    expect(screen.getByText('Knowledge base')).toBeInTheDocument();
  });
});
