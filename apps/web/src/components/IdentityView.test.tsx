import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { useIdentity } from '../state/identity';
import { patient } from '../test/fixtures';
import { server } from '../test/server';
import { renderWithClient } from '../test/utils';
import { IdentityView } from './IdentityView';

describe('IdentityView', () => {
  beforeEach(() => {
    useIdentity.setState({ phone: null });
    localStorage.clear();
  });

  it('validates the phone client-side before sending', async () => {
    const user = userEvent.setup();
    renderWithClient(<IdentityView />);
    await user.type(screen.getByLabelText('Phone number'), '123');
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.getByText('Enter a valid phone number.')).toBeInTheDocument();
    expect(useIdentity.getState().phone).toBeNull();
  });

  it('upserts the patient and holds the identity on success', async () => {
    const user = userEvent.setup();
    renderWithClient(<IdentityView />);
    await user.type(screen.getByLabelText('Phone number'), '0771234567');
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    await waitFor(() => {
      expect(useIdentity.getState().phone).toBe(patient.phone);
    });
  });

  it('surfaces a server error without holding an identity', async () => {
    server.use(
      http.post('/api/patients', () =>
        HttpResponse.json({ error: { code: 'bad', message: 'Phone rejected.' } }, { status: 422 }),
      ),
    );
    const user = userEvent.setup();
    renderWithClient(<IdentityView />);
    await user.type(screen.getByLabelText('Phone number'), '0771234567');
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findByText('Phone rejected.')).toBeInTheDocument();
    expect(useIdentity.getState().phone).toBeNull();
  });
});
