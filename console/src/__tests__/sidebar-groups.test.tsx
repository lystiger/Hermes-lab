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
  it('groups pages into three areas, and keeps project tools out of it', () => {
    installLiveHermes();
    render(<MemoryRouter><Sidebar /></MemoryRouter>);
    const nav = screen.getByRole('navigation', { name: 'Pages' });
    const groups = within(nav).getAllByRole('group').map((g) => [
      g.getAttribute('aria-label'),
      within(g).getAllByRole('link').map((l) => l.textContent?.replace(/\d+|live/g, '').trim())
    ]);
    expect(groups).toEqual([
      ['Overview', ['Dashboard', 'Queue', 'Review']],
      ['Live', ['Floor', 'Events', 'Comms']],
      ['System', ['Agents', 'Usage', 'Execution', 'Settings']]
    ]);
    expect(within(nav).queryByRole('link', { name: /Design/ })).not.toBeInTheDocument();
  });
});
