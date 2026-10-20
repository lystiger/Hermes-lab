import { describe, it, expect, vi } from 'vitest';

// Mock fixtures are opt-in: this file explicitly turns them on to check the persistent banner.
vi.hoisted(() => {
  process.env.VITE_LYSCONTROL_MOCK = '1';
});

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Layout } from '../components/Layout';
import { isMockMode } from '../api/client';

describe('M1 mock opt-in', () => {
  it('shows a persistent MOCK DATA banner when fixtures are requested', () => {
    expect(isMockMode).toBe(true);
    render(
      <MemoryRouter>
        <Layout />
      </MemoryRouter>
    );
    expect(screen.getByRole('status')).toHaveTextContent('MOCK DATA');
  });
});
