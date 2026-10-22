import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const hooks = vi.hoisted(() => ({
  useJobs: vi.fn(),
  useJob: vi.fn(),
  useAgents: vi.fn(),
}));

vi.mock('../api/hooks', () => hooks);

import FloorPage from '../routes/floor/index';

const T0 = Date.parse('2026-10-22T10:00:00Z');
const iso = (minutes: number) => new Date(T0 + minutes * 60_000).toISOString();

const jobs = [
  { id: 'job-1', title: 'Floor job', status: 'RUNNING' },
  { id: 'job-2', title: 'Old job', status: 'COMPLETED' },
];

// build is done, so harden-api (waiting only on the finished build) sits in level 1; verify waits on harden-api.
const details: Record<string, unknown> = {
  'job-1': {
    id: 'job-1',
    title: 'Floor job',
    status: 'RUNNING',
    phases: [
      { id: 'p-build', name: 'build', order: 1, role: 'builder', agentId: 'claude', status: 'SUCCEEDED', startedAt: iso(0), completedAt: iso(5) },
      { id: 'p-harden', name: 'harden-api', order: 2, role: 'hardener', agentId: 'codex', status: 'RUNNING', startedAt: iso(5), detail: 'patching router', dependencies: ['p-build'] },
      { id: 'p-verify', name: 'verify', order: 3, role: 'verifier', agentId: 'claude', status: 'PENDING', dependencies: ['p-harden'] },
    ],
    executionGraph: [],
  },
};

const agents = [
  { id: 'claude', displayName: 'Claude', accentColor: 'var(--lys-agent-claude)' },
  { id: 'codex', displayName: 'Codex' },
];

function renderPage() {
  hooks.useJobs.mockReturnValue({ jobs, loading: false, error: null, stale: false, updatedAt: null, refetch: vi.fn() });
  hooks.useAgents.mockReturnValue({ agents, loading: false, error: null, refetch: vi.fn(), updatedAt: null, stale: false });
  hooks.useJob.mockImplementation((id: string) => ({
    job: details[id] ?? null,
    loading: false,
    error: null,
    refetch: vi.fn(),
  }));
  return render(
    <MemoryRouter>
      <FloorPage />
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('Live floor page', () => {
  it('shows only active jobs', () => {
    renderPage();

    expect(screen.getByText('Floor job')).toBeInTheDocument();
    expect(screen.queryByText('Old job')).not.toBeInTheDocument();
  });

  it('places each phase in the column for its dependency level', () => {
    renderPage();

    const level1 = screen.getByRole('region', { name: 'Level 1' });
    const level2 = screen.getByRole('region', { name: 'Level 2' });
    expect(within(level1).getByText('builder')).toBeInTheDocument();
    expect(within(level1).getByText('hardener')).toBeInTheDocument();
    expect(within(level2).getByText('verifier')).toBeInTheDocument();
  });

  it('marks each card with the agent initial, its status and the live line', () => {
    renderPage();

    const hardener = screen.getByRole('article', { name: 'hardener, Running' });
    expect(within(hardener).getByText('C')).toBeInTheDocument();
    expect(within(hardener).getByText('Codex')).toBeInTheDocument();
    expect(within(hardener).getByText('patching router')).toBeInTheDocument();
  });

  it('renders cards with no buttons, because the page is read-only', () => {
    renderPage();

    const cards = screen.getAllByRole('article');
    expect(cards.length).toBeGreaterThan(0);
    for (const card of cards) {
      expect(within(card).queryAllByRole('button')).toHaveLength(0);
    }
  });
});
