import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Citations } from './Citations';

describe('Citations', () => {
  it('renders knowledge-base sources as document chips (no link)', () => {
    render(<Citations citations={['Visiting Hours & FAQs']} />);
    expect(screen.getByText('Sources')).toBeInTheDocument();
    const chip = screen.getByText('Visiting Hours & FAQs');
    expect(chip.closest('a')).toBeNull();
  });

  it('renders web sources as host chips linking to the URL', () => {
    render(<Citations citations={['https://www.example.org/traffic']} />);
    const link = screen.getByRole('link', { name: 'example.org' });
    expect(link).toHaveAttribute('href', 'https://www.example.org/traffic');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noreferrer noopener');
  });

  it('renders nothing when there are no citations', () => {
    const { container } = render(<Citations citations={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
