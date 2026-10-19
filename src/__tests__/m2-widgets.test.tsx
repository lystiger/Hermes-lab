import { describe, it, expect, vi, afterEach } from 'vitest';

vi.hoisted(() => {
  delete process.env.VITE_LYSCONTROL_MOCK;
});

import { act, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { JobDetailView } from '../features/jobs/JobDetailView';
import { ProviderTelemetryList } from '../features/telemetry/ProviderTelemetryList';
import { OperationalThreadView } from '../features/messaging/OperationalThreadView';
import { QueueRoute } from '../routes/queue';
import { useAgents } from '../api/hooks';
import { useConsoleStore } from '../stores/useConsoleStore';
import { CAPACITY_WINDOW_LABEL } from '../api/mapping';
import { installLiveHermes, LIVE_JOB_ID, LIVE_JOB_SUMMARY } from './support/liveHermes';

function renderIn(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

function countCalls(fetchMock: { mock: { calls: unknown[][] } }, pathname: string) {
  return fetchMock.mock.calls.filter(([u]) => new URL(String(u)).pathname === pathname).length;
}

afterEach(() => {
  vi.unstubAllGlobals();
  useConsoleStore.setState({ allEvents: [], activeModalJobId: null });
});

describe('M2 job detail: failure, tasks, runs, observations and trace', () => {
  it('explains the failure and shows the errors as errors', async () => {
    installLiveHermes();
    renderIn(<JobDetailView jobId={LIVE_JOB_ID} />);

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('Job failed after 2 phase(s)')).toBeInTheDocument();
    expect(within(alert).getByText('FAILED_TESTS: 1 test failed')).toBeInTheDocument();
    expect(within(alert).getByText('phase verify failed')).toBeInTheDocument();
  });

  it('shows tasks with their error text and the attempt count', async () => {
    installLiveHermes({
      tasks: [{ taskId: 'task_write', jobId: LIVE_JOB_ID, description: 'write the parser', status: 'FAILED', dependencies: ['task_plan'], requiredCapabilities: [], assignedActor: 'codex', parentTaskId: null, createdAt: null, startedAt: null, completedAt: null, attempt: 2, maxAttempts: 2, error: { type: 'TEST_FAIL', message: 'parser test red' }, supersededBy: null, artifactRefs: [] }]
    });
    renderIn(<JobDetailView jobId={LIVE_JOB_ID} />);

    expect(await screen.findByText('write the parser')).toBeInTheDocument();
    expect(screen.getByText('TASKS · 1')).toBeInTheDocument();
    expect(screen.getByText(/attempt 2 of 2/)).toBeInTheDocument();
    expect(screen.getByText('TEST_FAIL: parser test red')).toBeInTheDocument();
  });

  it('shows runs with the actor that ran them', async () => {
    installLiveHermes({
      runs: [{ run_id: 'run_verify_1', job_id: LIVE_JOB_ID, task_id: 'task_write', actor_id: 'codex', status: 'failed', attempt: 1, started_at: null, finished_at: null, exit_reason: 'tests', error: null, artifact_refs: [] }]
    });
    renderIn(<JobDetailView jobId={LIVE_JOB_ID} />);

    expect(await screen.findByText('run_verify_1')).toBeInTheDocument();
    expect(screen.getByText(/codex · task_write · attempt 1/)).toBeInTheDocument();
    expect(screen.getByText('exit: tests')).toBeInTheDocument();
  });

  it('shows observations with their kind and content', async () => {
    installLiveHermes({
      observations: [{ observation_id: 'obs_1', job_id: LIVE_JOB_ID, kind: 'discovery', content: 'fixtures drift from schema', task_id: null, actor_id: 'claude', source: null, confidence: 0.9, created_at: null }]
    });
    renderIn(<JobDetailView jobId={LIVE_JOB_ID} />);

    expect(await screen.findByText('fixtures drift from schema')).toBeInTheDocument();
    expect(screen.getByText(/discovery · claude · confidence 0.9/)).toBeInTheDocument();
  });

  it('says so when Hermes recorded no tasks, runs or observations (an answered empty, not an error)', async () => {
    installLiveHermes();
    renderIn(<JobDetailView jobId={LIVE_JOB_ID} />);

    expect(await screen.findByText('No tasks recorded')).toBeInTheDocument();
    expect(screen.getByText('No runs recorded')).toBeInTheDocument();
    expect(screen.getByText('No observations recorded')).toBeInTheDocument();
  });

  it('shows a failed task list as an error with retry, not as no tasks', async () => {
    installLiveHermes({ failSub: 'tasks' });
    renderIn(<JobDetailView jobId={LIVE_JOB_ID} />);

    expect(await screen.findByText('Tasks failed')).toBeInTheDocument();
    expect(screen.queryByText('No tasks recorded')).not.toBeInTheDocument();
  });

  it('shows the job token total with its window and says when none was tracked', async () => {
    installLiveHermes({ jobTokens: { input_tokens: 1200, output_tokens: 300, cached_tokens: 0, total_tokens: 1500 } });
    renderIn(<JobDetailView jobId={LIVE_JOB_ID} />);

    expect(await screen.findByText(/1500/)).toBeInTheDocument();
    expect(screen.getByText('tokens tracked for this job')).toBeInTheDocument();
  });

  it('merges durable history with the live buffer and marks each row by its origin', async () => {
    installLiveHermes({
      events: [{ event_id: 'evt_durable', job_id: LIVE_JOB_ID, event_type: 'job.failed', occurred_at: '2026-10-01T10:02:05Z', actor_id: 'codex', payload: { detail: 'verify failed' } }]
    });
    useConsoleStore.setState({
      allEvents: [
        { id: 'evt_live', ts: '10:00:00.000', rawTs: 2, source: { id: 'claude', kind: 'agent', displayName: 'Claude' }, kind: 'agent.started', detail: 'started', dur: '—', jobId: LIVE_JOB_ID }
      ]
    });
    renderIn(<JobDetailView jobId={LIVE_JOB_ID} />);

    expect(await screen.findByText('verify failed')).toBeInTheDocument();
    expect(screen.getByText('started')).toBeInTheDocument();
    expect(screen.getByText('durable')).toBeInTheDocument();
    expect(screen.getByText('live')).toBeInTheDocument();
  });

  it('shows a failed durable history fetch as an error while keeping the live rows', async () => {
    installLiveHermes({ failSub: 'events' });
    useConsoleStore.setState({
      allEvents: [
        { id: 'evt_live_only', ts: '10:00:00.000', rawTs: 2, source: { id: 'claude', kind: 'agent', displayName: 'Claude' }, kind: 'agent.started', detail: 'live detail', dur: '—', jobId: LIVE_JOB_ID }
      ]
    });
    renderIn(<JobDetailView jobId={LIVE_JOB_ID} />);

    expect(await screen.findByText('Durable job history failed')).toBeInTheDocument();
    expect(screen.getByText('live detail')).toBeInTheDocument();
  });
});

describe('M2 provider telemetry: labelled as process lifetime, never daily', () => {
  it('shows provider usage with its source, window label and unknown remaining values', async () => {
    installLiveHermes({
      capacity: {
        timestamp: '2026-10-14T08:00:00+00:00',
        summary: { total_providers: 1, total_requests: 3, total_failures: 1, total_throttling_events: 0, total_tokens: 900, input_tokens: 600, output_tokens: 300, cached_tokens: 0 },
        providers: {
          claude: {
            provider_id: 'claude', status: 'available', status_reason: null, total_requests: 3, success_count: 2, failure_count: 1,
            success_rate: 0.6667, throttling_count: 0, failure_breakdown: { http_500: 1 },
            usage: { provider_id: 'claude', actor_id: 'claude', input_tokens: 600, output_tokens: 300, cached_tokens: 0, requests_used: 3, requests_remaining: null, request_limit: null, tokens_used: 900, tokens_remaining: null, token_limit: null, context_window: null, context_used: null, reset_at: null, observed_at: '2026-10-14T08:00:00+00:00', source: 'provider_reported' }
          }
        },
        jobs_tracked: 1
      }
    });
    const { container } = renderIn(<ProviderTelemetryList />);

    expect(await screen.findByText('claude')).toBeInTheDocument();
    expect(screen.getByText('provider reported')).toBeInTheDocument();
    expect(screen.getAllByText('since runtime start (process lifetime, not daily)').length).toBeGreaterThan(0);
    expect(screen.getByText('67%')).toBeInTheDocument();
    // Remaining requests are not reported, so they are unknown rather than a number.
    expect(screen.getByLabelText('unknown: Provider did not report a remaining request count')).toBeInTheDocument();
    // The window label itself says "not daily"; everything else must not imply a daily figure.
    const text = (container.textContent ?? '').split(CAPACITY_WINDOW_LABEL).join('');
    expect(text).not.toMatch(/today|daily|per day/i);
  });

  it('labels an estimate as estimated, not as provider reported', async () => {
    installLiveHermes({
      capacity: {
        summary: null,
        providers: { codex: { provider_id: 'codex', status: 'available', total_requests: 0, success_count: 0, failure_count: 0, success_rate: 1.0, throttling_count: 0, failure_breakdown: {}, usage: { source: 'hermes_estimated', tokens_used: 4000 } } },
        jobs_tracked: 0
      }
    });
    renderIn(<ProviderTelemetryList />);

    expect(await screen.findByText('estimated by Hermes')).toBeInTheDocument();
    expect(screen.queryByText('provider reported')).not.toBeInTheDocument();
    // No requests yet, so the registry's 100% is not shown as a rate.
    expect(screen.getByLabelText(/No requests have been made/)).toBeInTheDocument();
  });

  it('shows an honest empty state for an empty registry', async () => {
    installLiveHermes();
    renderIn(<ProviderTelemetryList />);
    expect(await screen.findByText('No provider usage')).toBeInTheDocument();
  });

  it('shows the capacity error with retry when the report cannot be loaded', async () => {
    const fetchMock = installLiveHermes();
    fetchMock.fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      return { ok: url.pathname !== '/capacity/telemetry', status: url.pathname === '/capacity/telemetry' ? 500 : 200, statusText: 'Internal Server Error', json: async () => ({}) } as unknown as Response;
    });
    renderIn(<ProviderTelemetryList />);
    expect(await screen.findByText(/Provider telemetry failed/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'retry' })).toBeInTheDocument();
  });
});

describe('M2 recoverable jobs and thread errors', () => {
  it('lists recoverable jobs read-only, with no resume or cancel controls', async () => {
    installLiveHermes({ recoverable: [{ ...LIVE_JOB_SUMMARY, status: 'RUNNING' }] });
    renderIn(<QueueRoute />);

    expect((await screen.findAllByText(LIVE_JOB_ID)).length).toBeGreaterThan(0);
    expect(screen.getByText(/Recoverable · 1 · read-only/)).toBeInTheDocument();
    // Exact action names only: the queue's "Cancelled" status filter is not an action.
    expect(screen.queryByRole('button', { name: /^(resume|cancel)( job)?$/i })).not.toBeInTheDocument();
  });

  it('shows a missing thread as an error, not as an empty conversation', async () => {
    installLiveHermes({ threadMissing: true });
    renderIn(<OperationalThreadView threadId="thread_job_gone" />);

    expect(await screen.findByText('Operational messages failed')).toBeInTheDocument();
    expect(screen.getByText(/HTTP 404/)).toBeInTheDocument();
    expect(screen.queryByText(/No operational messages/)).not.toBeInTheDocument();
  });
});

describe('M2 refresh after reconnect and on relevant events', () => {
  function AgentsProbe() {
    const { agents } = useAgents();
    return <div>agents:{agents.length}</div>;
  }

  it('refetches agent identity after the stream resyncs', async () => {
    const { fetchMock } = installLiveHermes();
    renderIn(<AgentsProbe />);
    await screen.findByText('agents:3');
    const before = countCalls(fetchMock, '/agents');

    act(() => useConsoleStore.getState().markRuntimeResynced());

    await waitFor(() => expect(countCalls(fetchMock, '/agents')).toBeGreaterThan(before));
  });

  it('refetches agent identity when an agent event arrives', async () => {
    const { fetchMock } = installLiveHermes();
    renderIn(<AgentsProbe />);
    await screen.findByText('agents:3');
    const before = countCalls(fetchMock, '/agents');

    act(() =>
      useConsoleStore.getState().addTraceEvent({
        id: 'evt_agent_started',
        ts: '10:00:00.000',
        rawTs: 3,
        source: { id: 'claude', kind: 'agent', displayName: 'Claude' },
        kind: 'agent.started',
        detail: 'started',
        dur: '—'
      })
    );

    await waitFor(() => expect(countCalls(fetchMock, '/agents')).toBeGreaterThan(before));
  });
});
