import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';

vi.hoisted(() => {
  delete process.env.VITE_LYSCONTROL_MOCK;
});

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ConnectionBanner } from '../components/ConnectionBanner';
import { JobModal } from '../components/JobModal';
import { CopyId } from '../components/CopyId';
import { QueueRoute } from '../routes/queue';
import { EventsRoute } from '../routes/events';
import { UsageRoute } from '../routes/usage';
import { AgentsListRoute } from '../routes/agents/index';
import { AgentDetailRoute } from '../routes/agents/$agentId';
import { ExecutionResourceCard } from '../features/execution/ExecutionResourceCard';
import { useAgents } from '../api/hooks';
import { resetConnectionForTests } from '../api/connection';
import { useConsoleStore } from '../stores/useConsoleStore';
import { formatDateTime, formatTimeOfDay, UNKNOWN_TIME } from '../features/time/format';
import { groupOf } from '../features/jobs/MissionBoard';
import { eventCategory, eventSeverity } from '../features/events/eventKinds';
import { installLiveHermes, LIVE_JOB_ID, LIVE_JOB_SUMMARY } from './support/liveHermes';
import { TraceEvent } from '../api/types';

function renderIn(ui: React.ReactElement, path = '/') {
  return render(<MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>);
}

beforeEach(() => {
  resetConnectionForTests();
  useConsoleStore.setState({ allEvents: [], activeModalJobId: null, eFilter: 'All' });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  resetConnectionForTests();
});

describe('M3 connection: unmistakable when Hermes cannot be reached', () => {
  function Probe() {
    const { agents } = useAgents();
    return <div>agents:{agents.length}</div>;
  }

  it('shows a banner with the API URL, last successful contact and a retry, then clears on recovery', async () => {
    const options: { unreachable?: boolean } = {};
    installLiveHermes(options);
    renderIn(
      <>
        <ConnectionBanner />
        <Probe />
      </>
    );
    await screen.findByText('agents:3');
    expect(screen.queryByText(/CAN'T REACH HERMES/)).not.toBeInTheDocument();

    // Hermes goes down; the next request fails at the network level.
    options.unreachable = true;
    act(() => useConsoleStore.getState().markRuntimeResynced());

    const banner = await screen.findByRole('alert');
    expect(banner).toHaveTextContent("CAN'T REACH HERMES");
    expect(banner).toHaveTextContent('API http://localhost:8000');
    // The last successful contact is named, not hidden.
    expect(banner).toHaveTextContent(/last successful contact \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/);

    // Hermes comes back; retry re-requests and the banner clears.
    options.unreachable = false;
    fireEvent.click(within(banner).getByRole('button', { name: 'retry' }));
    await waitFor(() => expect(screen.queryByText(/CAN'T REACH HERMES/)).not.toBeInTheDocument());
  });

  it('says "can\'t reach Hermes" on a data panel instead of looking empty', async () => {
    installLiveHermes({ unreachable: true });
    renderIn(<QueueRoute />);

    // Each panel that needs Hermes says so; none of them looks empty.
    expect((await screen.findAllByText("Can't reach Hermes")).length).toBeGreaterThan(0);
    expect(screen.queryByText('No jobs returned by Hermes.')).not.toBeInTheDocument();
  });

  it('reports "none this session" when Hermes was never reached', async () => {
    installLiveHermes({ unreachable: true });
    renderIn(
      <>
        <ConnectionBanner />
        <Probe />
      </>
    );
    expect(await screen.findByText(/last successful contact none this session/)).toBeInTheDocument();
  });
});

describe('M3 keyboard: Escape closes, arrows move, focus is visible', () => {
  it('Escape closes the job inspector', async () => {
    installLiveHermes();
    useConsoleStore.setState({ activeModalJobId: LIVE_JOB_ID });
    renderIn(<JobModal />);
    expect(await screen.findByRole('dialog', { name: `Job ${LIVE_JOB_ID}` })).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(useConsoleStore.getState().activeModalJobId).toBeNull();
  });

  it('arrow keys move focus through the agent roster', async () => {
    installLiveHermes();
    renderIn(
      <Routes>
        <Route path="/agents" element={<AgentsListRoute />} />
      </Routes>,
      '/agents'
    );
    const options = await screen.findAllByRole('option');
    expect(options.length).toBe(3);
    options[0].focus();
    fireEvent.keyDown(options[0], { key: 'ArrowDown' });
    expect(document.activeElement).toBe(options[1]);
    fireEvent.keyDown(options[1], { key: 'End' });
    expect(document.activeElement).toBe(options[2]);
    fireEvent.keyDown(options[2], { key: 'Home' });
    expect(document.activeElement).toBe(options[0]);
  });

  it('arrow keys move focus through the job board', async () => {
    installLiveHermes({ jobs: [LIVE_JOB_SUMMARY, { ...LIVE_JOB_SUMMARY, id: 'job-b', title: 'Second job', status: 'FAILED' }] });
    renderIn(<QueueRoute />);
    const first = (await screen.findAllByRole('button', { name: LIVE_JOB_SUMMARY.title }))[0];
    first.focus();
    fireEvent.keyDown(first, { key: 'ArrowDown' });
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Second job' }));
  });

  it('copyable IDs copy to the clipboard and say so', async () => {
    const writeText = vi.fn(async () => undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });
    renderIn(<CopyId value="run_123" />);
    fireEvent.click(screen.getByRole('button', { name: 'Copy run_123' }));
    expect(writeText).toHaveBeenCalledWith('run_123');
    expect(await screen.findByText('copied')).toBeInTheDocument();
  });
});

describe('M3 time: one local format across the console', () => {
  it('formats local time and shows unknown for missing or invalid input', () => {
    const d = new Date(2026, 9, 14, 7, 5, 9);
    expect(formatTimeOfDay(d)).toBe('07:05:09');
    expect(formatDateTime(d)).toBe('2026-10-14 07:05:09');
    expect(formatDateTime(null)).toBe(UNKNOWN_TIME);
    expect(formatTimeOfDay('not a date')).toBe(UNKNOWN_TIME);
  });
});

describe('M3 agents: roster and dossier with only real fields', () => {
  it('shows the roster with real counts, and the dossier for the selected agent', async () => {
    installLiveHermes();
    renderIn(
      <Routes>
        <Route path="/agents/:agentId" element={<AgentDetailRoute />} />
      </Routes>,
      '/agents/claude'
    );

    const dossier = await screen.findByRole('article', { name: 'Dossier for Claude' });
    expect(within(dossier).getByText('Anthropic')).toBeInTheDocument();
    expect(within(dossier).getByText('claude-opus')).toBeInTheDocument();
    expect(within(dossier).getByText('plan')).toBeInTheDocument();
    // Hermes reports no current task or tool, so those read as unknown with a reason.
    expect(within(dossier).getAllByTitle('Hermes reports no current task for this agent').length).toBeGreaterThan(0);
    expect(within(dossier).getByRole('button', { name: /dispatch task/i })).toBeDisabled();
    expect(screen.getByRole('group', { name: 'Filter agents by status' })).toBeInTheDocument();
  });

  it('filters the roster by real status and counts each status', async () => {
    installLiveHermes();
    renderIn(
      <Routes>
        <Route path="/agents" element={<AgentsListRoute />} />
      </Routes>,
      '/agents'
    );
    await screen.findAllByRole('option');
    const idle = screen.getByRole('button', { name: /idle\s*3/i });
    fireEvent.click(idle);
    expect(idle).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getAllByRole('option').length).toBe(3);
    expect(screen.queryByRole('button', { name: /running/i })).not.toBeInTheDocument();
  });
});

describe('M3 queue: mission board grouped by real status', () => {
  it('groups each job into exactly one column by its status', () => {
    expect(groupOf({ ...LIVE_JOB_SUMMARY, status: 'PLANNING' } as any).id).toBe('RUNNING');
    expect(groupOf({ ...LIVE_JOB_SUMMARY, status: 'CLAIMED' } as any).id).toBe('QUEUED');
    expect(groupOf({ ...LIVE_JOB_SUMMARY, status: 'FAILED' } as any).id).toBe('FAILED');
    expect(groupOf({ ...LIVE_JOB_SUMMARY, status: 'MYSTERY' } as any)).toMatchObject({ id: 'OTHER:MYSTERY', label: 'Other · MYSTERY' });
  });

  it('shows column headings with counts, a mission-interrupted note for failures, and no invented priority', async () => {
    installLiveHermes({
      jobs: [
        { ...LIVE_JOB_SUMMARY, id: 'job-run', title: 'Running one', status: 'RUNNING', progress: 0.4 },
        { ...LIVE_JOB_SUMMARY, id: 'job-fail', title: 'Failed one', status: 'FAILED', priority: undefined }
      ]
    });
    renderIn(<QueueRoute />);

    expect(await screen.findByRole('list', { name: 'Running jobs' })).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Failed jobs' })).toBeInTheDocument();
    expect(screen.getByText(/MISSION INTERRUPTED/)).toBeInTheDocument();
    expect(screen.getAllByRole('progressbar', { name: 'Job progress' })[0]).toHaveAttribute('aria-valuenow', '40');
    // Hermes reports no priority for this job, so none is shown.
    const failedList = screen.getByRole('list', { name: 'Failed jobs' });
    expect(within(failedList).queryByText('P1')).not.toBeInTheDocument();
  });
});

describe('M3 events: filterable log with the failure taxonomy', () => {
  const event = (id: string, kind: string, source = 'Claude'): TraceEvent => ({
    id,
    ts: '10:00:00.000',
    rawTs: 1791964651,
    source: { id: source.toLowerCase(), kind: 'agent', displayName: source },
    kind,
    detail: `${kind} detail`,
    dur: '—',
    jobId: LIVE_JOB_ID,
    runId: 'run_x',
    actorId: source.toLowerCase(),
    metadata: { k: 1 }
  });

  it('classifies failures and warnings separately from normal events', () => {
    expect(eventCategory('job.failed')).toBe('failures');
    expect(eventCategory('execution.release_failed')).toBe('failures');
    expect(eventCategory('quota.warn')).toBe('warnings');
    expect(eventCategory('agent.started')).toBe('agents');
    expect(eventSeverity('agent.finished')).toBe('ok');
    expect(eventSeverity('job.failed')).toBe('error');
  });

  it('filters by category with live counts and expands a row to its JSON with IDs', async () => {
    useConsoleStore.setState({
      allEvents: [event('e1', 'job.failed', 'Codex'), event('e2', 'agent.started'), event('e3', 'agent.finished')]
    });
    renderIn(<EventsRoute />, '/events');

    fireEvent.click(screen.getByRole('button', { name: /^Failures\s*1/ }));
    expect(screen.getByText('job.failed')).toBeInTheDocument();
    expect(screen.queryByText('agent.started')).not.toBeInTheDocument();
    expect(screen.getByText('1 of 3 shown')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^All\s*3/ }));
    fireEvent.click(screen.getByRole('button', { name: /job\.failed/ }));
    expect(screen.getByText(/"kind": "job.failed"/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy run_x' })).toBeInTheDocument();
  });

  it('filters by source', () => {
    useConsoleStore.setState({ allEvents: [event('e1', 'agent.started', 'Claude'), event('e2', 'agent.started', 'Codex')] });
    renderIn(<EventsRoute />, '/events');
    fireEvent.click(screen.getByRole('button', { name: /^Codex\s*1/ }));
    expect(screen.getByRole('log', { name: 'Events' }).querySelectorAll('[data-nav-item]').length).toBe(1);
  });
});

describe('M3 usage: meters with window labels', () => {
  it('labels each total with its window and draws no bar for an unreported limit', async () => {
    installLiveHermes({
      capacity: {
        summary: { total_providers: 1, total_requests: 4, total_failures: 1, total_throttling_events: 2, total_tokens: 800, input_tokens: 500, output_tokens: 300, cached_tokens: 0 },
        providers: {
          claude: {
            provider_id: 'claude', status: 'available', total_requests: 4, success_count: 3, failure_count: 1, success_rate: 0.75, throttling_count: 2, failure_breakdown: {},
            usage: { source: 'provider_reported', tokens_used: 800, requests_remaining: null, request_limit: null, token_limit: null, context_window: null, context_used: null, reset_at: null }
          }
        },
        jobs_tracked: 1
      }
    });
    renderIn(<UsageRoute />);

    const providerSection = await screen.findByRole('region', { name: 'Meters for claude' });
    // Tokens are reported without a limit: a value, a window label, and no meter bar.
    expect(within(providerSection).getByText('800 tok')).toBeInTheDocument();
    expect(within(providerSection).queryByRole('progressbar', { name: 'TOKENS USED' })).not.toBeInTheDocument();
    // Context is not reported: unknown, with the reason.
    expect(within(providerSection).getByLabelText('unknown: Provider did not report context use')).toBeInTheDocument();
    // Every total says which window it covers.
    expect(screen.getAllByText(/since runtime start \(process lifetime, not daily\)/).length).toBeGreaterThan(2);
    // Aggregate and provider success rates are both 3 of 4.
    for (const meter of screen.getAllByRole('progressbar', { name: 'SUCCESS RATE' })) {
      expect(meter).toHaveAttribute('aria-valuenow', '75');
    }
  });
});

describe('M3 execution: seat cards', () => {
  it('numbers each seat and keeps its ID copyable', () => {
    const resource = {
      backend: 'openrig', kind: 'seat', id: 'seat-7', label: 'Seat seven', state: 'running' as const,
      jobId: 'job-1', taskId: null, executionId: null, since: '2026-10-14T00:00:00Z', expiresAt: null, details: {}
    };
    render(<ExecutionResourceCard resource={resource as any} nowMs={Date.now()} seat={2} />);
    expect(screen.getByText('SEAT 02')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy seat-7' })).toBeInTheDocument();
  });
});
