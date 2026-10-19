import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.hoisted(() => {
  delete process.env.VITE_LYSCONTROL_MOCK;
});

import { HttpHermesApi } from '../api/adapters/httpAdapter';
import { installLiveHermes, LIVE_JOB_ID, LIVE_JOB_SUMMARY } from './support/liveHermes';

describe('M2 HTTP adapter (GET only, observed shapes)', () => {
  let api: HttpHermesApi;

  beforeEach(() => {
    api = new HttpHermesApi('http://localhost:8000');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('reads capacity telemetry from GET /capacity/telemetry', async () => {
    const { requests } = installLiveHermes();
    const c = await api.getCapacityTelemetry();
    expect(requests).toContain('/capacity/telemetry');
    expect(c.summary!.totalTokens).toBe(0);
  });

  it('reads job token telemetry from GET /jobs/{id}/telemetry', async () => {
    const { requests } = installLiveHermes();
    const t = await api.getJobTelemetry(LIVE_JOB_ID);
    expect(requests).toContain(`/jobs/${LIVE_JOB_ID}/telemetry`);
    expect(t.totalTokens).toBe(0);
  });

  it('reads tasks, runs and observations for a job', async () => {
    const { requests } = installLiveHermes({
      tasks: [{ taskId: 't1', jobId: LIVE_JOB_ID, description: 'd', status: 'RUNNING', dependencies: [], requiredCapabilities: [], assignedActor: 'codex', createdAt: null, startedAt: null, completedAt: null, attempt: 1, maxAttempts: 2, error: null, supersededBy: null, artifactRefs: [] }],
      runs: [{ run_id: 'run_1', job_id: LIVE_JOB_ID, task_id: 't1', actor_id: 'codex', status: 'running', attempt: 1, started_at: null, finished_at: null, exit_reason: null, error: null, artifact_refs: [] }],
      observations: [{ observation_id: 'o1', job_id: LIVE_JOB_ID, kind: 'discovery', content: 'c', task_id: null, actor_id: null, source: null, confidence: 1, created_at: null }]
    });
    expect((await api.getJobTasks(LIVE_JOB_ID))[0].assignedActor).toBe('codex');
    expect((await api.getJobRuns(LIVE_JOB_ID))[0].runId).toBe('run_1');
    expect((await api.getJobObservations(LIVE_JOB_ID))[0].observationId).toBe('o1');
    expect(requests).toEqual(expect.arrayContaining([`/jobs/${LIVE_JOB_ID}/tasks`, `/jobs/${LIVE_JOB_ID}/runs`, `/jobs/${LIVE_JOB_ID}/observations`]));
  });

  it('reads durable job history with a limit and normalises the stored envelope', async () => {
    const { requests } = installLiveHermes({
      events: [{ event_id: 'evt_s', job_id: LIVE_JOB_ID, event_type: 'job.failed', occurred_at: '2026-10-01T10:02:05Z', actor_id: null, payload: { detail: 'x' } }]
    });
    const events = await api.getJobEvents(LIVE_JOB_ID, 100);
    expect(requests).toContain(`/jobs/${LIVE_JOB_ID}/events?limit=100`);
    expect(events[0]).toMatchObject({ id: 'evt_s', kind: 'job.failed', jobId: LIVE_JOB_ID, actorId: null });
  });

  it('surfaces a failed sub-resource as an error rather than an empty list', async () => {
    installLiveHermes({ failSub: 'tasks' });
    await expect(api.getJobTasks(LIVE_JOB_ID)).rejects.toThrow('HTTP 500');
  });

  it('surfaces a missing thread (404) as an error, not as an empty conversation', async () => {
    installLiveHermes({ threadMissing: true });
    await expect(api.getMessages('thread_job_gone')).rejects.toThrow('HTTP 404');
  });

  it('lists recoverable jobs read-only from GET /jobs/recoverable', async () => {
    const { requests } = installLiveHermes({ recoverable: [{ ...LIVE_JOB_SUMMARY, status: 'RUNNING' }] });
    const jobs = await api.getRecoverableJobs();
    expect(requests).toContain('/jobs/recoverable');
    expect(jobs[0]).toMatchObject({ id: LIVE_JOB_ID, status: 'RUNNING' });
  });

  it('keeps runId and actorId on the live trace history', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => [{ id: 'evt_1', ts: '10:00:00.000', rawTs: 1, source: { id: 'claude', kind: 'agent', displayName: 'Claude' }, kind: 'agent.started', detail: 'go', dur: '—', jobId: 'job_1', taskId: 't1', runId: 'run_7', actorId: 'claude' }]
    }) as unknown as Response));
    const [e] = await api.getTraceEvents(10);
    expect(e).toMatchObject({ runId: 'run_7', actorId: 'claude', jobId: 'job_1' });
  });

  it('keeps runId and actorId on the live SSE stream', async () => {
    const instances: any[] = [];
    class FakeEventSource {
      listeners: Record<string, (ev: { data: string }) => void> = {};
      onmessage: ((ev: { data: string }) => void) | null = null;
      onerror: ((ev: unknown) => void) | null = null;
      constructor(public url: string) {
        instances.push(this);
      }
      addEventListener(name: string, fn: (ev: { data: string }) => void) {
        this.listeners[name] = fn;
      }
      removeEventListener() {}
      close() {}
    }
    vi.stubGlobal('EventSource', FakeEventSource);

    const received: any[] = [];
    api.subscribeEvents((e) => received.push(e));
    const es = instances[0];
    es.listeners.trace({
      data: JSON.stringify({ id: 'evt_sse', ts: '10:00:01.000', rawTs: 2, source: { id: 'codex', kind: 'agent', displayName: 'Codex' }, kind: 'job.failed', detail: 'x', dur: '—', jobId: 'job_9', taskId: null, runId: 'run_3', actorId: 'codex' })
    });
    expect(received[0]).toMatchObject({ id: 'evt_sse', runId: 'run_3', actorId: 'codex', taskId: null });
  });
});
