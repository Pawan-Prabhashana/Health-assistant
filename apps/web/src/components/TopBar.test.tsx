import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { useSessionState } from '../state/session';
import { patient } from '../test/fixtures';
import { renderWithClient } from '../test/utils';
import { TopBar } from './TopBar';

describe('TopBar', () => {
  beforeEach(() => {
    useSessionState.setState({ activeSessionId: null, view: 'chat', sidebarOpen: false });
  });

  // The menu control is a mobile affordance (CSS display:none at desktop widths),
  // so it is queried by its label rather than by an accessible role.
  it('toggles the sidebar drawer from the menu button in chat view', async () => {
    const user = userEvent.setup();
    renderWithClient(<TopBar patient={patient} />);
    const menu = screen.getByLabelText('Open conversations');
    expect(menu).toHaveAttribute('aria-expanded', 'false');

    await user.click(menu);
    expect(useSessionState.getState().sidebarOpen).toBe(true);
    expect(menu).toHaveAttribute('aria-expanded', 'true');
  });

  it('does not render the menu button on the status view', () => {
    useSessionState.setState({ view: 'health' });
    renderWithClient(<TopBar patient={patient} />);
    expect(screen.queryByLabelText('Open conversations')).toBeNull();
  });

  it('renders no menu button before identity', () => {
    renderWithClient(<TopBar patient={null} />);
    expect(screen.queryByLabelText('Open conversations')).toBeNull();
  });
});
