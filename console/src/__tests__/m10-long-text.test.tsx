import { afterEach, describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import * as hooks from '../api/hooks';
import { useConsoleStore } from '../stores/useConsoleStore';
import { JobDetailView } from '../features/jobs/JobDetailView';
import { cleanup, render, screen, within } from '@testing-library/react';
import { QueueTable } from '../features/jobs/QueueTable';
import { phaseLabel } from '../features/jobs/runTimeline';
import { MissionBoard } from '../features/jobs/MissionBoard';
import { LONG_TEXT_JOB, LONG_PROMPT_PATH, LONG_JOB_ID, MockHermesApi } from '../api/adapters/mockAdapter';

vi.mock('../api/hooks', async (orig) => ({ ...(await orig<typeof import('../api/hooks')>()), useAgents: () => ({ agents: [] }) }));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  useConsoleStore.setState({ allEvents: [], activeModalJobId: null });
});

describe('Long queue values', () => {
  it('keeps a 90+ character path and 60 character ID in bounded cells with full tooltips', () => {
    expect(LONG_PROMPT_PATH.length).toBeGreaterThanOrEqual(90);
    expect(LONG_JOB_ID).toHaveLength(60);
    render(<QueueTable jobs={[LONG_TEXT_JOB]} />);
    for (const value of [LONG_PROMPT_PATH, LONG_JOB_ID]) {
      expect(screen.getByTitle(value)).toHaveClass('min-w-0', 'truncate');
      expect(screen.getByTitle(value)).toHaveTextContent(value);
    }
  });

  it('preserves truncation and copy access on the Queue mission board', () => {
    render(<MissionBoard jobs={[LONG_TEXT_JOB]} loading={false} error={null} updatedAt={null} onRetry={() => {}} onOpen={() => {}} />);
    for (const value of [LONG_PROMPT_PATH, LONG_JOB_ID]) {
      expect(screen.getByTitle(value)).toHaveClass('truncate');
    }
    expect(screen.getByRole('button', { name: `Copy ${LONG_JOB_ID}` })).toBeInTheDocument();
  });

  it('serves the same long fixture in mock queue, inspector phases and traces', async () => {
    const api = new MockHermesApi();
    expect(await api.getJobs()).toContainEqual(LONG_TEXT_JOB);
    expect((await api.getJob(LONG_JOB_ID))?.phases?.[0].name).toBe(LONG_PROMPT_PATH);
    expect((await api.getTraceEvents())[0].source.displayName).toBe('Hermes.scheduler');
    expect(await api.getJobEvents(LONG_JOB_ID)).toHaveLength(1);
  });
});

describe('Inspector long values', () => {
  it.each(['stored', 'bus', 'live'] as const)('preserves the phase path and hidden trace metadata for %s events', async (origin) => {
    const api = new MockHermesApi();
    const job = (await api.getJob(LONG_JOB_ID))!;
    vi.spyOn(hooks, 'useJob').mockReturnValue({ job, loading: false, error: null, updatedAt: null, stale: false, refetch: vi.fn() });
    const [event] = await api.getJobEvents(LONG_JOB_ID);
    const traceEvent = { ...event, dur: '1.2s', ...(origin === 'bus' ? { origin: 'bus' as const } : {}) };
    vi.spyOn(hooks, 'useJobEvents').mockReturnValue({ events: origin === 'live' ? [] : [traceEvent], loading: false, error: null, updatedAt: null, stale: false, refetch: vi.fn() });
    useConsoleStore.setState({ allEvents: origin === 'live' ? [traceEvent] : [] });
    render(<MemoryRouter><JobDetailView jobId={LONG_JOB_ID} /></MemoryRouter>);
    // The phase shows the file name but its tooltip must hold the whole path.
    const phase = screen.getByText(phaseLabel(LONG_PROMPT_PATH));
    expect(phase).toHaveAttribute('title', LONG_PROMPT_PATH);
    // Duration and durability columns are hidden below xl (e.g. 900 px), so the kind tooltip carries them.
    const label = origin === 'stored' ? 'durable' : origin === 'bus' ? 'in-memory' : 'live';
    const kind = screen.getByTitle(`task.created · 1.2s · ${label}`);
    expect(kind).toHaveTextContent('task.created');
    expect(kind).not.toHaveClass('hidden');
    const row = kind.parentElement!;
    expect(within(row).getByText('1.2s')).toHaveClass('hidden', 'xl:block');
    expect(within(row).getByText(label)).toHaveClass('hidden', 'xl:block');
  });
});
