import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.hoisted(() => {
  delete process.env.VITE_LYSCONTROL_MOCK;
});

import { Sidebar } from '../components/Sidebar';
import { installLiveHermes } from './support/liveHermes';

afterEach(() => vi.unstubAllGlobals());

describe('sidebar navigation', () => {
  it('groups pages by what the operator is doing, and keeps project tools out of it', () => {
    installLiveHermes();
    render(<MemoryRouter><Sidebar /></MemoryRouter>);
    const nav = screen.getByRole('navigation', { name: 'Pages' });
    const groups = within(nav).getAllByRole('group').map((g) => [
      g.getAttribute('aria-label'),
      within(g).getAllByRole('link').map((l) => l.textContent?.replace(/\d+|live/g, '').trim())
    ]);
    expect(groups).toEqual([
      ['Run', ['Overview', 'Floor', 'Review', 'Queue']],
      ['Ask', ['Comms']],
      ['Agents', ['Agents', 'Usage']],
      ['System', ['Events', 'Execution', 'Settings']]
    ]);
    expect(within(nav).queryByRole('link', { name: /Design/ })).not.toBeInTheDocument();
  });
});
