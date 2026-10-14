import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';

vi.hoisted(() => {
  delete process.env.VITE_LYSCONTROL_MOCK;
});

import { act, fireEvent, render, renderHook, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { useAgent, useJob, useJobTelemetry } from '../api/hooks';
import { hermesApi } from '../api/client';
import { HttpHermesApi } from '../api/adapters/httpAdapter';
import { getConnection, resetConnectionForTests } from '../api/connection';
import { AgentDetail, JobDetail, Message, TraceEvent } from '../api/types';
import { useConsoleStore } from '../stores/useConsoleStore';
import { JobDetailView } from '../features/jobs/JobDetailView';
import { JobTokens } from '../features/jobs/JobRealData';
import { OperationalThreadView } from '../features/messaging/OperationalThreadView';
import { installLiveHermes, LIVE_JOB_DETAIL, LIVE_JOB_ID } from './support/liveHermes';

/** A promise the test resolves or rejects by hand, to control the order of responses. */
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((a, b) => {
    resolve = a;
    reject = b;
  });
  return { promise, resolve, reject };
}

function makeAgent(id: string, name: string): AgentDetail {
  return {
    id,
    displayName: name,
    provider: 'p',
    model: 'm',
    role: 'r',
    capabilities: [],
    status: 'IDLE',
    input: '—',
    output: '—',
    cached: '—',
    remaining: '—',
    inPct: '—',
    outPct: '—',
    cachePct: '—',
    activity: [],
    metrics: [],
    runs: [],
    allowance: [],
    capacity: '—',
    reset: '—',
    resetNote: ''
  };
}

function bumpJobVersion() {
  act(() => {
    useConsoleStore.setState({ jobRuntimeVersion: useConsoleStore.getState().jobRuntimeVersion + 1 });
  });
}

beforeEach(() => {
  resetConnectionForTests();
  useConsoleStore.setState({ allEvents: [], activeModalJobId: null });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('M5 F1: selected identity and job data are keyed and sequenced', () => {
  it('agent: when B resolves before A, the screen shows B and never A', async () => {
    const a = deferred<AgentDetail | null>();
    const b = deferred<AgentDetail | null>();
    vi.spyOn(hermesApi, 'getAgent').mockImplementation((id: string) => (id === 'a' ? a.promise : b.promise));

    const { result, rerender } = renderHook(({ id }) => useAgent(id), { initialProps: { id: 'a' as string | undefined } });
    rerender({ id: 'b' });
    await act(async () => b.resolve(makeAgent('b', 'Bravo')));
    expect(result.current.agent?.id).toBe('b');

    await act(async () => a.resolve(makeAgent('a', 'Alpha')));
    expect(result.current.agent?.id).toBe('b');
    expect(result.current.agent?.displayName).toBe('Bravo');
  });

  it('agent: an old response that resolves after the switch is dropped even when the new one is still pending', async () => {
    const a = deferred<AgentDetail | null>();
    const b = deferred<AgentDetail | null>();
    vi.spyOn(hermesApi, 'getAgent').mockImplementation((id: string) => (id === 'a' ? a.promise : b.promise));

    const { result, rerender } = renderHook(({ id }) => useAgent(id), { initialProps: { id: 'a' as string | undefined } });
    rerender({ id: 'b' });
    await act(async () => a.resolve(makeAgent('a', 'Alpha')));
    // B is still pending: nothing from A may appear.
    expect(result.current.agent).toBeNull();
    await act(async () => b.resolve(makeAgent('b', 'Bravo')));
    expect(result.current.agent?.id).toBe('b');
  });

  it('agent: a refresh of the same agent that fails keeps its data and reports the error', async () => {
    const spy = vi.spyOn(hermesApi, 'getAgent');
    spy.mockResolvedValueOnce(makeAgent('a', 'Alpha'));
    spy.mockRejectedValueOnce(new Error('Hermes /agents returned HTTP 500: Internal Server Error'));

    const { result } = renderHook(() => useAgent('a'));
    await waitFor(() => expect(result.current.agent?.id).toBe('a'));
    await act(async () => result.current.refetch());
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.agent?.id).toBe('a');
    expect(result.current.stale).toBe(true);
  });

  it('job: an older RUNNING detail that resolves after a newer COMPLETED refresh cannot overwrite it', async () => {
    const first = deferred<JobDetail | null>();
    const second = deferred<JobDetail | null>();
    const spy = vi.spyOn(hermesApi, 'getJob');
    spy.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);

    const { result } = renderHook(() => useJob(LIVE_JOB_ID));
    bumpJobVersion();
    await act(async () => second.resolve({ ...(LIVE_JOB_DETAIL as any), status: 'COMPLETED' }));
    expect(result.current.job?.status).toBe('COMPLETED');
    await act(async () => first.resolve({ ...(LIVE_JOB_DETAIL as any), status: 'RUNNING' }));
    expect(result.current.job?.status).toBe('COMPLETED');
  });

  it('job: switching to another job that fails shows nothing from the first job', async () => {
    const spy = vi.spyOn(hermesApi, 'getJob');
    spy.mockResolvedValueOnce({ ...(LIVE_JOB_DETAIL as any), id: 'job-a', title: 'Job A' });
    spy.mockRejectedValueOnce(new Error('Hermes /jobs/job-b returned HTTP 500: Internal Server Error'));

    const { result, rerender } = renderHook(({ id }) => useJob(id), { initialProps: { id: 'job-a' as string | null } });
    await waitFor(() => expect(result.current.job?.id).toBe('job-a'));
    rerender({ id: 'job-b' });
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.job).toBeNull();
  });

  it('telemetry is keyed by job: B failing never shows A totals', async () => {
    const spy = vi.spyOn(hermesApi, 'getJobTelemetry');
    spy.mockResolvedValueOnce({ jobId: 'job-a', inputTokens: 1, outputTokens: 2, cachedTokens: 0, totalTokens: 3 });
    spy.mockRejectedValueOnce(new Error('Hermes /jobs/job-b/telemetry returned HTTP 500'));

    const { result, rerender } = renderHook(({ id }) => useJobTelemetry(id), { initialProps: { id: 'job-a' as string | null } });
    await waitFor(() => expect(result.current.telemetry?.totalTokens).toBe(3));
    rerender({ id: 'job-b' });
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.telemetry ?? null).toBeNull();
  });
});

describe('M5 F2: a failed refresh after a good load is stale, with error and retry', () => {
  it('keeps the last token total, labels it stale, and offers retry', async () => {
    const spy = vi.spyOn(hermesApi, 'getJobTelemetry');
    spy.mockResolvedValueOnce({ jobId: LIVE_JOB_ID, inputTokens: 1000, outputTokens: 500, cachedTokens: 0, totalTokens: 1500 });
    spy.mockRejectedValueOnce(new Error('Hermes /jobs/x/telemetry returned HTTP 500: Internal Server Error'));

    render(<JobTokens jobId={LIVE_JOB_ID} />);
    expect(await screen.findByText(/1500/)).toBeInTheDocument();

    bumpJobVersion();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('stale: refresh failed');
    expect(screen.getByText(/1500/)).toBeInTheDocument();
    expect(within(alert).getByRole('button', { name: 'retry' })).toBeInTheDocument();
  });

  it('shows the job detail as stale with its error and last-loaded time after a failed refresh', async () => {
    const spy = vi.spyOn(hermesApi, 'getJob');
    spy.mockResolvedValueOnce(LIVE_JOB_DETAIL as any);
    spy.mockRejectedValueOnce(new Error('Hermes /jobs/J returned HTTP 500: Internal Server Error'));

    render(
      <MemoryRouter>
        <JobDetailView jobId={LIVE_JOB_ID} />
      </MemoryRouter>
    );
    expect(await screen.findByText('Live runner end-to-end')).toBeInTheDocument();

    bumpJobVersion();
    expect(await screen.findByText(/refresh failed, showing last loaded data: Hermes \/jobs\/J returned HTTP 500/)).toBeInTheDocument();
    // The old detail stays on screen, marked as stale.
    expect(screen.getByText('Live runner end-to-end')).toBeInTheDocument();
    expect(screen.getAllByText(/last loaded/).length).toBeGreaterThan(0);
  });

  it('an HTTP error response is not counted as successful contact with Hermes', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 500, statusText: 'Internal Server Error', json: async () => ({}) }) as unknown as Response));
    const api = new HttpHermesApi('http://localhost:8000');
    await expect(api.getHealth()).rejects.toThrow('HTTP 500');
    expect(getConnection().lastContactAt).toBeNull();
    expect(getConnection().reachable).toBe(true);
  });

  it('a successful response is counted as contact', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, statusText: 'OK', json: async () => ({ status: 'ok', service: 'hermes', version: '0', uptimeSeconds: 1, timestamp: 'x' }) }) as unknown as Response));
    await new HttpHermesApi('http://localhost:8000').getHealth();
    expect(getConnection().lastContactAt).not.toBeNull();
  });
});

describe('M5 F3: a reply carries its reply context, and clears only on success', () => {
  const thread = 'thr_m5';
  const replied: Message = {
    id: 'msg_m5_1',
    threadId: thread,
    from: { id: 'claude', kind: 'agent', displayName: 'Claude' },
    to: [],
    kind: 'handoff',
    text: 'Please confirm the migration',
    conversationId: 'conv_9',
    correlationId: 'corr_3',
    artifactRefs: [],
    metadata: {},
    createdAt: '2026-10-14T07:00:00Z'
  };

  function renderThread() {
    vi.spyOn(hermesApi, 'getMessages').mockResolvedValue([replied]);
    return render(<OperationalThreadView threadId={thread} />);
  }

  it('sends replyTo, conversationId and correlationId from the message replied to', async () => {
    const send = vi.spyOn(hermesApi, 'sendMessage').mockResolvedValue({} as Message);
    renderThread();
    fireEvent.click(await screen.findByTitle('Reply to this message'));
    expect(screen.getByText(/Replying to msg_m5_1/)).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/Send operational guidance/), { target: { value: 'confirmed' } });
    fireEvent.click(screen.getByRole('button', { name: 'DISPATCH' }));

    await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    expect(send).toHaveBeenCalledWith(thread, 'confirmed', ['claude'], 'operator', 'operator_note', 'conv_9', 'msg_m5_1', 'corr_3');
    await waitFor(() => expect(screen.queryByText(/Replying to msg_m5_1/)).not.toBeInTheDocument());
  });

  it('a failed send keeps the typed text and the reply target', async () => {
    vi.spyOn(hermesApi, 'sendMessage').mockRejectedValue(new Error('Hermes POST /messages returned HTTP 500'));
    renderThread();
    fireEvent.click(await screen.findByTitle('Reply to this message'));
    const composer = screen.getByPlaceholderText(/Send operational guidance/) as HTMLInputElement;
    fireEvent.change(composer, { target: { value: 'confirmed' } });
    fireEvent.click(screen.getByRole('button', { name: 'DISPATCH' }));

    expect(await screen.findByText(/Message not sent/)).toBeInTheDocument();
    expect(composer.value).toBe('confirmed');
    expect(screen.getByText(/Replying to msg_m5_1/)).toBeInTheDocument();
  });
});

describe('M5 F4: verification, retry history and repair/replan counts render from the job', () => {
  it('shows verification results, attempts and counts that Hermes reported', async () => {
    vi.spyOn(hermesApi, 'getJob').mockResolvedValue({
      ...(LIVE_JOB_DETAIL as any),
      status: 'COMPLETED',
      verification: { status: 'PASSED', results: [{ name: 'pytest', passed: 14, failed: 0 }] },
      retryHistory: [{ attempt: 2, phase: 'verify', status: 'failed', note: 'flaky network' }],
      repairCount: 2,
      replanCount: 0
    });
    render(
      <MemoryRouter>
        <JobDetailView jobId={LIVE_JOB_ID} />
      </MemoryRouter>
    );
    expect(await screen.findByText('status: PASSED')).toBeInTheDocument();
    expect(screen.getByText(/name: pytest · passed: 14 · failed: 0/)).toBeInTheDocument();
    expect(screen.getByText(/attempt: 2 · phase: verify · status: failed · note: flaky network/)).toBeInTheDocument();
    expect(screen.getByText('REPAIRS').parentElement).toHaveTextContent('2');
    expect(screen.getByText('REPLANS').parentElement).toHaveTextContent('0');
  });

  it('says what is unavailable instead of inventing totals, retry limits or pass counts', async () => {
    vi.spyOn(hermesApi, 'getJob').mockResolvedValue({ ...(LIVE_JOB_DETAIL as any), verification: null, retryHistory: undefined, repairCount: undefined, replanCount: undefined });
    render(
      <MemoryRouter>
        <JobDetailView jobId={LIVE_JOB_ID} />
      </MemoryRouter>
    );
    expect(await screen.findByText('Hermes recorded no verification result for this job.')).toBeInTheDocument();
    expect(screen.getByText('not reported by Hermes for this job')).toBeInTheDocument();
    expect(screen.getByTitle('Hermes did not report a repair count')).toBeInTheDocument();
    expect(screen.getByTitle('Hermes did not report a replan count')).toBeInTheDocument();
    expect(screen.queryByText(/of 3|retries used|maxRetries/)).not.toBeInTheDocument();
  });
});

describe('M5 F5: only canonical stored envelopes are durable', () => {
  const busShaped = {
    id: 'evt_bus_1',
    ts: '10:00:00.000',
    rawTs: 1791964651,
    source: { id: 'hermes', kind: 'runtime', displayName: 'Hermes Runtime' },
    kind: 'job.failed',
    detail: 'bus only',
    dur: '—',
    jobId: LIVE_JOB_ID,
    taskId: null,
    runId: null,
    actorId: null,
    metadata: {}
  };

  it('the adapter marks a bus-shaped job-history response as bus, not stored', async () => {
    installLiveHermes({ events: [busShaped] });
    const events: TraceEvent[] = await new HttpHermesApi('http://localhost:8000').getJobEvents(LIVE_JOB_ID, 10);
    expect(events[0].origin).toBe('bus');
  });

  it('the job view labels bus-fallback history as in-memory and never as durable', async () => {
    installLiveHermes({ events: [busShaped] });
    render(
      <MemoryRouter>
        <JobDetailView jobId={LIVE_JOB_ID} />
      </MemoryRouter>
    );
    expect(await screen.findByText('bus only')).toBeInTheDocument();
    expect(screen.getByText('in-memory')).toBeInTheDocument();
    expect(screen.queryByText('durable')).not.toBeInTheDocument();
  });

  it('a canonical stored envelope is labelled durable', async () => {
    installLiveHermes({
      events: [{ event_id: 'evt_store_9', job_id: LIVE_JOB_ID, event_type: 'job.failed', occurred_at: '2026-10-01T10:02:05Z', actor_id: null, payload: { detail: 'stored only' } }]
    });
    render(
      <MemoryRouter>
        <JobDetailView jobId={LIVE_JOB_ID} />
      </MemoryRouter>
    );
    expect(await screen.findByText('stored only')).toBeInTheDocument();
    expect(screen.getByText('durable')).toBeInTheDocument();
  });
});
