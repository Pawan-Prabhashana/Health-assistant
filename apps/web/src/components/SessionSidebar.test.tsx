import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { useSessionState } from '../state/session';
import { patient, session } from '../test/fixtures';
import { server } from '../test/server';
import { renderWithClient } from '../test/utils';
import { SessionSidebar } from './SessionSidebar';

describe('SessionSidebar', () => {
  beforeEach(() => {
    useSessionState.setState({ activeSessionId: null, view: 'chat' });
  });

  it('lists the patient sessions', async () => {
    renderWithClient(<SessionSidebar phone={patient.phone} />);
    expect(await screen.findByText('General enquiry')).toBeInTheDocument();
  });

  it('creates a session and makes it active', async () => {
    const user = userEvent.setup();
    renderWithClient(<SessionSidebar phone={patient.phone} />);
    await screen.findByText('General enquiry');
    await user.click(screen.getByRole('button', { name: 'New' }));
    await waitFor(() => {
      expect(useSessionState.getState().activeSessionId).toBe(session.id);
    });
  });

  it('deletes a session and clears the active selection', async () => {
    useSessionState.setState({ activeSessionId: session.id, view: 'chat' });
    const user = userEvent.setup();
    renderWithClient(<SessionSidebar phone={patient.phone} />);
    await screen.findByText('General enquiry');
    await user.click(screen.getByRole('button', { name: `Delete ${session.title}` }));
    await waitFor(() => {
      expect(useSessionState.getState().activeSessionId).toBeNull();
    });
  });

  it('shows an error state when the list cannot load', async () => {
    server.use(http.get('/api/sessions', () => new HttpResponse(null, { status: 500 })));
    renderWithClient(<SessionSidebar phone={patient.phone} />);
    expect(await screen.findByText('Could not load conversations.')).toBeInTheDocument();
  });

  it('shows an empty state when there are no sessions', async () => {
    server.use(http.get('/api/sessions', () => HttpResponse.json([])));
    renderWithClient(<SessionSidebar phone={patient.phone} />);
    expect(await screen.findByText('No conversations yet. Start a new one.')).toBeInTheDocument();
  });
});
