import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// HTTP is the default. These tests render real routes against the observed live sample only.
vi.hoisted(() => {
  delete process.env.VITE_LYSCONTROL_MOCK;
});

import { act, render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { OverviewRoute } from '../routes/index';
import { QueueRoute } from '../routes/queue';
import { UsageRoute } from '../routes/usage';
import { AgentDetailRoute } from '../routes/agents/$agentId';
import { EventsRoute } from '../routes/events';
import { JobDetailView } from '../features/jobs/JobDetailView';
import { Sidebar } from '../components/Sidebar';
import { OperationalThreadView } from '../features/messaging/OperationalThreadView';
import { hermesApi } from '../api/client';
import { Route, Routes } from 'react-router-dom';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useExecutionStore } from '../stores/useExecutionStore';
import { EMPTY_EXECUTION_VIEW } from '../stores/executionReducer';
import { TraceEvent } from '../api/types';
import { installLiveHermes, LIVE_JOB_ID } from './support/liveHermes';

/** Figures and claims that no Hermes endpoint backs. None may appear on an HTTP-mode screen. */
const FABRICATED = [
  '$4.12',
  '58%',
  '173k',
  '246k',
  '284K',
  '91k',
  '~12k',
  '~9k',
  '~37 min',
  '~11 min',
  '34 runs',
  '#142',
  '#148',
  'Redis',
  'redis-state',
  'moveinmate',
  'EXACT',
  '666',
  '1,500',
  'SIMULATED DEMO',
  'control-plane://active',
  'serial per repository',
  'governed · serial',
  'Human Review Required',
  'HARDEN',
  'auto-merge',
  'Raise cap',
  'raise cap',
  'Sprint cap raised',
  'projected overrun',
  '200k',
  '30%',
  '50k',
  '0k',
  'trc claude',
  'historical medians',
  'Online'
];

function flatText(container: HTMLElement): string {
  return container.textContent ?? '';
}

function expectNoFabrication(container: HTMLElement) {
  const text = flatText(container);
  const found = FABRICATED.filter((needle) => text.includes(needle));
  expect(found, `fabricated text on screen: ${found.join(', ')}`).toEqual([]);
}

function renderIn(ui: React.ReactElement, path = '/') {
  return render(<MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>);
}

/** Renders an agent route the way the app does, so its :agentId param is set. */
function renderAgent(agentId: string) {
  return render(
    <MemoryRouter initialEntries={[`/agents/${agentId}`]}>
      <Routes>
        <Route path="/agents/:agentId" element={<AgentDetailRoute />} />
      </Routes>
    </MemoryRouter>
  );
}

/** Text of the value cell next to a metric label such as "FAILED 24H". */
function metricValue(label: string): string {
  const cell = screen.getByText(label).parentElement!;
  return cell.textContent?.replace(label, '').trim() ?? '';
}

describe('M1 truth sweep: HTTP-mode screens render only real data', () => {
  beforeEach(() => {
    useConsoleStore.setState({ allEvents: [], activeModalJobId: null, eFilter: 'All' });
    useExecutionStore.setState({ view: EMPTY_EXECUTION_VIEW, snapshotStatus: 'idle', buffer: null, latestRequest: 0 });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('Overview: counts are derived from the job list and nothing is invented', async () => {
    installLiveHermes();
    const { container } = renderIn(<OverviewRoute />);

    expect(await screen.findByText('No active execution')).toBeInTheDocument();
    await waitFor(() => expect(metricValue('RUNNING')).toBe('0'));
    expect(metricValue('QUEUED')).toBe('0');
    expect(metricValue('BLOCKED')).toBe('0');
    expect(metricValue('FAILED 24H')).toBe('0');
    expect(metricValue('TOKENS TODAY')).toBe('—');
    expect(metricValue('EST. SPEND')).toBe('—');
    expect(screen.getByText(/counts from the latest 1 jobs/)).toBeInTheDocument();

    expect(await screen.findByText('No provider usage reported. Hermes provider telemetry is not connected in this build.')).toBeInTheDocument();
    expectNoFabrication(container);
  });

  it('Overview: an active job is shown with its real id, not the removed #142 placeholder', async () => {
    installLiveHermes({
      jobs: [{ id: 'job-live-9', title: 'Real active job', repository: 'org/repo', branch: 'main', status: 'RUNNING', assignedAgentIds: [], startedAt: new Date(Date.now() - 65_000).toISOString() }]
    });
    const { container } = renderIn(<OverviewRoute />);

    // The id appears in the active card and the queue shortlist; both must carry the real job.
    expect((await screen.findAllByText('job-live-9')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Real active job').length).toBeGreaterThan(0);
    expect(screen.queryByText('No active execution')).not.toBeInTheDocument();
    expect(screen.getByText(/elapsed/)).toBeInTheDocument();
    expectNoFabrication(container);
  });

  it('Queue: no active job, so no execution order or estimate claims are shown', async () => {
    installLiveHermes();
    const { container } = renderIn(<QueueRoute />);

    expect(await screen.findByText('No active job. Nothing is executing in the latest jobs from Hermes.')).toBeInTheDocument();
    expect(screen.getByText(/time estimates: not available/)).toBeInTheDocument();
    expect(container.textContent).not.toContain(LIVE_JOB_ID.slice(0, 8) + ' · build');
    expectNoFabrication(container);
  });

  it('Usage: states that values are not measured instead of showing a demo banner or budget numbers', async () => {
    installLiveHermes();
    const { container } = renderIn(<UsageRoute />);

    expect(await screen.findByText(/Usage is not measured in this build/)).toBeInTheDocument();
    expect(screen.getByText('2 · RUN BUDGET')).toBeInTheDocument();
    expect(screen.getByText('not reported by Hermes')).toBeInTheDocument();
    expectNoFabrication(container);
  });

  it('Agent detail: context, token, activity and run values are unknown, not zero or placeholders', async () => {
    installLiveHermes();
    const { container } = renderAgent('claude');

    expect(await screen.findByRole('heading', { name: 'Claude' })).toBeInTheDocument();
    expect(screen.getByText('Run history is not loaded. No runs endpoint is wired for agents yet, so this is unknown rather than empty.')).toBeInTheDocument();
    expect(screen.getByText('Provider quota is not reported by Hermes for this agent.')).toBeInTheDocument();
    expect(screen.getByText('Activity is not loaded in this build. Live events for this agent appear in Events.')).toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
    expectNoFabrication(container);
  });

  it('Job detail: elapsed comes from the job timestamps and no policy is claimed', async () => {
    installLiveHermes();
    const { container } = renderIn(<JobDetailView jobId={LIVE_JOB_ID} />);

    // 09:00:00 → 10:02:05 is a finished job, so the elapsed value is fixed at 1:02:05.
    expect(await screen.findByText('1:02:05')).toBeInTheDocument();
    expect(screen.getByText('Live runner end-to-end')).toBeInTheDocument();
    expectNoFabrication(container);
  });

  it('Events: the Errors filter includes live failure kinds', async () => {
    installLiveHermes();
    const failure: TraceEvent = {
      id: 'evt_fail_1',
      ts: '10:02:05.000',
      rawTs: 1791961700,
      source: { id: 'codex', kind: 'agent', displayName: 'Codex' },
      kind: 'job.failed',
      detail: 'verify failed',
      dur: '—'
    };
    const ok: TraceEvent = { ...failure, id: 'evt_ok_1', kind: 'agent.started', detail: 'started verify' };
    useConsoleStore.setState({ allEvents: [failure, ok] });
    const { container } = renderIn(<EventsRoute />, '/events');

    fireEvent.click(screen.getByRole('button', { name: 'Errors' }));
    expect(screen.getByText('job.failed')).toBeInTheDocument();
    expect(screen.queryByText('agent.started')).not.toBeInTheDocument();
    expectNoFabrication(container);
  });

  it('Events: a list filtered to nothing says so rather than showing an empty table silently', async () => {
    installLiveHermes();
    renderIn(<EventsRoute />, '/events');
    fireEvent.click(screen.getByRole('button', { name: 'Tools' }));
    expect(screen.getByText('No events received yet.')).toBeInTheDocument();
  });

  it('Sidebar: Herdr is shown as available on PATH, not online, and Hermes status comes from the connection', async () => {
    installLiveHermes();
    await useExecutionStore.getState().refreshSnapshot();
    const { container } = renderIn(<Sidebar />);

    expect(await screen.findByText('Available')).toBeInTheDocument();
    expect(screen.queryByText('Online')).not.toBeInTheDocument();
    expect(screen.queryByText('Connected')).not.toBeInTheDocument();
    expectNoFabrication(container);
  });

  it('Operator dispatch is disabled and reports why, instead of claiming a control plane', async () => {
    installLiveHermes();
    renderAgent('claude');
    const input = await screen.findByPlaceholderText('Operator commands are not available yet');
    expect(input).toBeDisabled();
    expect(screen.getByText(/nothing is sent from here/)).toBeInTheDocument();
  });
});

describe('M1 error and retry states', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows the real fetch error instead of zeros when the job list fails', async () => {
    installLiveHermes({ failJobs: true });
    const { container } = renderIn(<OverviewRoute />);

    expect(await screen.findByText(/Metrics unavailable: Hermes \/jobs returned HTTP 500/)).toBeInTheDocument();
    expect(screen.getAllByRole('alert').some((el) => el.textContent?.includes('Job queue failed'))).toBe(true);
    expect(container.textContent).not.toContain('RUNNING');
  });

  it('keeps the last loaded queue visible but labels it stale when a refresh fails', async () => {
    const options: { failJobs?: boolean } = {};
    installLiveHermes(options);
    renderIn(<OverviewRoute />);
    expect((await screen.findAllByText(LIVE_JOB_ID)).length).toBeGreaterThan(0);

    // A job event triggers a refetch of the job list; that refetch now fails.
    options.failJobs = true;
    act(() => {
      useConsoleStore.setState({ jobRuntimeVersion: useConsoleStore.getState().jobRuntimeVersion + 1 });
    });

    expect(await screen.findByText(/Job queue refresh failed, showing last loaded data/)).toBeInTheDocument();
    expect(screen.getAllByText(LIVE_JOB_ID).length).toBeGreaterThan(0);
  });

  it('retries a failed job list when asked', async () => {
    const { fetchMock } = installLiveHermes({ failJobs: true });
    renderIn(<QueueRoute />);

    expect(await screen.findByText(/Job queue failed/)).toBeInTheDocument();
    const before = fetchMock.mock.calls.filter(([u]) => new URL(String(u)).pathname === '/jobs').length;
    const queueAlert = screen.getAllByRole('alert').find((el) => el.textContent?.includes('Job queue failed'))!;
    fireEvent.click(within(queueAlert).getByRole('button', { name: 'retry' }));
    await waitFor(() => {
      const after = fetchMock.mock.calls.filter(([u]) => new URL(String(u)).pathname === '/jobs').length;
      expect(after).toBeGreaterThan(before);
    });
  });

  it('keeps the typed message and announces the failure when a thread send fails', async () => {
    installLiveHermes();
    vi.spyOn(hermesApi, 'sendMessage').mockRejectedValue(new Error('Hermes POST /messages returned HTTP 503: Service Unavailable'));
    renderIn(<OperationalThreadView threadId="thread_job_live" />);

    const composer = await screen.findByPlaceholderText('Send operational guidance into job thread...');
    fireEvent.change(composer, { target: { value: 'please re-run verify' } });
    fireEvent.click(screen.getByRole('button', { name: 'DISPATCH' }));

    expect(await screen.findByText(/Message not sent: Hermes POST \/messages returned HTTP 503/)).toBeInTheDocument();
    expect((composer as HTMLInputElement).value).toBe('please re-run verify');
    vi.restoreAllMocks();
  });
});
