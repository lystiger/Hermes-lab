import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { hermesApi } from '../api/client';
import { UsageRoute } from '../routes/usage';
import { AgentLimit } from '../api/types';

const claude: AgentLimit = {
  id: 'claude', name: 'Claude', plan: 'Max 5x', ready: true, stale: false, status: 'ok',
  usedPct: 14, leftPct: 86, resetsAt: '2026-10-20T10:10:00Z', resetsInSeconds: 7800,
  windows: [
    { label: '5h', usedPct: 14, leftPct: 86, resetsAt: '2026-10-20T10:10:00Z', resetsInSeconds: 7800 },
    { label: 'Weekly', usedPct: 6, leftPct: 94, resetsAt: null, resetsInSeconds: 0 }
  ],
  updatedAt: '2026-10-20T07:59:00Z', authHelp: ''
};
const codex: AgentLimit = {
  id: 'codex', name: 'Codex', plan: '', ready: false, stale: false, status: 'ok',
  usedPct: 0, leftPct: 100, resetsAt: null, resetsInSeconds: 0, windows: [],
  updatedAt: null, authHelp: 'Run codex login to sign in.'
};

beforeEach(() => {
  vi.spyOn(hermesApi, 'getAgentLimits').mockResolvedValue({ timestamp: null, agents: [claude, codex] });
  vi.spyOn(hermesApi, 'getCapacityTelemetry').mockResolvedValue({ providers: [], summary: null, jobsTracked: null, timestamp: null });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('Usage route', () => {
  it('shows what is left for each agent', async () => {
    render(<MemoryRouter><UsageRoute /></MemoryRouter>);

    const card = await screen.findByRole('region', { name: 'Limits for Claude' });
    // Headline number plus the 5h window row.
    expect(within(card).getAllByText('86%')).toHaveLength(2);
    expect(within(card).getByText('left')).toBeInTheDocument();
    expect(within(card).getByText(/Max 5x/)).toBeInTheDocument();
    expect(within(card).getByText('ok')).toBeInTheDocument();
    expect(within(card).getByText('resets in 2h 10m')).toBeInTheDocument();
    expect(within(card).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '86');
    expect(within(card).getByText('5h')).toBeInTheDocument();
    expect(within(card).getByText('94%')).toBeInTheDocument();
  });

  it('shows the auth help instead of a bar when an agent is not ready', async () => {
    render(<MemoryRouter><UsageRoute /></MemoryRouter>);

    const card = await screen.findByRole('region', { name: 'Limits for Codex' });
    expect(within(card).getByText('not ready')).toBeInTheDocument();
    expect(within(card).getByText('Run codex login to sign in.')).toBeInTheDocument();
    expect(within(card).queryByRole('progressbar')).not.toBeInTheDocument();
    expect(within(card).queryByText(/resets in/)).not.toBeInTheDocument();
  });

  it('shows dashes for missing totals', async () => {
    render(<MemoryRouter><UsageRoute /></MemoryRouter>);
    await screen.findByRole('region', { name: 'Limits for Claude' });
    expect(screen.getByText('TOKENS').nextElementSibling).toHaveTextContent('—');
    expect(screen.getByText('THROTTLING').nextElementSibling).toHaveTextContent('—');
  });
});
