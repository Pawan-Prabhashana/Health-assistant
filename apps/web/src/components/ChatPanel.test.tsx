import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http } from 'msw';
import { describe, expect, it } from 'vitest';

import { makeChatResponse } from '../test/fixtures';
import { sseResponse, streamFrames } from '../test/handlers';
import { patient, session } from '../test/fixtures';
import { server } from '../test/server';
import { renderWithClient } from '../test/utils';
import { ChatPanel } from './ChatPanel';

describe('ChatPanel', () => {
  it('renders persisted history with its route and citations', async () => {
    renderWithClient(<ChatPanel sessionId={session.id} phone={patient.phone} />);
    expect(await screen.findByText('Our visiting hours are 10am to 8pm.')).toBeInTheDocument();
    expect(screen.getByText('Knowledge base')).toBeInTheDocument();
    expect(screen.getByText('Visiting Hours')).toBeInTheDocument();
  });

  it('streams a reply token by token and renders the final answer', async () => {
    const user = userEvent.setup();
    renderWithClient(<ChatPanel sessionId={session.id} phone={patient.phone} />);
    await screen.findByText('Our visiting hours are 10am to 8pm.');

    await user.type(screen.getByLabelText('Message'), 'Hello');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByText('Hello')).toBeInTheDocument();
    const answers = await screen.findAllByText('Hello, welcome to Sahana.');
    expect(answers.length).toBeGreaterThan(0);
  });

  it('renders a streamed refusal as a calm boundary', async () => {
    server.use(
      http.post('/api/chat/stream', () =>
        sseResponse(
          streamFrames(
            makeChatResponse({
              verdict: 'out_of_scope',
              route: null,
              answer: 'I can only answer questions related to hospital services.',
            }),
          ),
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithClient(<ChatPanel sessionId={session.id} phone={patient.phone} />);
    await screen.findByText('Our visiting hours are 10am to 8pm.');

    await user.type(screen.getByLabelText('Message'), 'Tell me a joke');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByText('Outside what I can help with')).toBeInTheDocument();
    const refusals = await screen.findAllByText(
      'I can only answer questions related to hospital services.',
    );
    expect(refusals.length).toBeGreaterThan(0);
  });
});
