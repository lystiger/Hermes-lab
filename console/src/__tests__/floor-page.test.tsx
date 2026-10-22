import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import type { JobPhase } from '../api/types';

const hooks = vi.hoisted(() => ({ useAgents: vi.fn(), useJob: vi.fn(), useJobs: vi.fn(), useJobTelemetry: vi.fn(() => ({ telemetry: null })) }));
vi.mock('../api/hooks', () => hooks);

import { FloorRoute } from '../routes/floor';
import { useConsoleStore } from '../stores/useConsoleStore';

const NOW = Date.parse('2026-10-22T10:00:00Z');
const phases: JobPhase[] = [
  { id: 'running', name: 'build', order: 1, role: 'builder', agentId: 'codex', status: 'RUNNING', startedAt: new Date(NOW - 125_000).toISOString() },
  { id: 'failed', name: 'harden', order: 2, role: 'hardener', status: 'FAILED' },
  { id: 'done', name: 'verify', order: 3, role: 'verifier', status: 'SUCCEEDED', startedAt: new Date(NOW - 60_000).toISOString(), completedAt: new Date(NOW - 5000).toISOString() },
  { id: 'queued', name: 'publish', order: 4, role: 'publisher', status: 'PENDING' },
];

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  useConsoleStore.setState({ allEvents: [] });
  const result = { loading: false, error: null, updatedAt: null, refetch: vi.fn() };
  hooks.useJobs.mockReturnValue({ ...result, jobs: [{ id: 'job-1', title: 'Active job', status: 'RUNNING' }] });
  hooks.useJob.mockReturnValue({ ...result, job: { id: 'job-1', phases, executionGraph: [] } });
  hooks.useAgents.mockReturnValue({ ...result, agents: [{ id: 'codex', displayName: 'Codex', accentColor: '#123456' }] });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('Floor page cards', () => {
  it.each([
    ['builder', 'Running', '--lys-status-success'],
    ['hardener', 'Failed', '--lys-status-danger'],
    ['verifier', 'Done', '--lys-text-muted'],
    ['publisher', 'Queued', '--lys-text-faint'],
  ])('renders %s as %s with its status color', (role, label, color) => {
    render(<FloorRoute />);
    const card = screen.getByRole('article', { name: `${role} · ${label}` });
    expect(within(card).getByText(label)).toHaveStyle({ color: `var(${color})` });
  });

  it('renders every phase in spec order in one column when dependency edges are unavailable', () => {
    render(<FloorRoute />);
    const section = screen.getByRole('region', { name: 'Active job' });
    const cards = within(section).getAllByRole('article');
    expect(cards.map((card) => card.getAttribute('aria-label'))).toEqual([
      'builder · Running', 'hardener · Failed', 'verifier · Done', 'publisher · Queued',
    ]);
    expect(new Set(cards.map((card) => card.parentElement)).size).toBe(1);
    expect(within(cards[0]).getByText('Codex')).toBeInTheDocument();
    expect(within(cards[0]).getByText('2m 05s')).toBeInTheDocument();
    expect(within(cards[2]).getByText('55s')).toBeInTheDocument();
    expect(within(cards[3]).getByText('—', { selector: '.font-mono-code' })).toBeInTheDocument();
    expect(hooks.useJob).toHaveBeenCalledWith('job-1');
  });

  it('switches between the card and timeline views of a job, and shows its spend', () => {
    hooks.useJobTelemetry.mockReturnValue({ telemetry: { costUsd: 0.0125, totalTokens: 52_000, tasks: [] } });
    render(<FloorRoute />);
    expect(screen.getByText('$0.0125 · 52.0k tokens')).toBeInTheDocument();
    const cards = screen.getByRole('button', { name: 'Cards' });
    const timeline = screen.getByRole('button', { name: 'Timeline' });
    expect(cards).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(timeline);
    expect(timeline).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByLabelText('Run timeline')).toBeInTheDocument();
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
  });
});
