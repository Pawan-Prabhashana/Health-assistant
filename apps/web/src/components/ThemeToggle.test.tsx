import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { useThemeStore } from '../state/theme';
import { ThemeToggle } from './ThemeToggle';

describe('ThemeToggle', () => {
  beforeEach(() => {
    useThemeStore.setState({ theme: 'system' });
    document.documentElement.removeAttribute('data-theme');
    localStorage.clear();
  });

  it('cycles system → light → dark and drives the document data-theme', async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);
    const button = screen.getByRole('button');

    // system: no explicit attribute.
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);

    await user.click(button);
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(useThemeStore.getState().theme).toBe('light');

    await user.click(button);
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');

    await user.click(button);
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
    expect(useThemeStore.getState().theme).toBe('system');
  });
});
