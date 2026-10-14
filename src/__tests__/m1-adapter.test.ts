import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// HTTP is the default. Mock fixtures are opt-in only (rule 2), so make sure this file never sees them.
vi.hoisted(() => {
  delete process.env.VITE_LYSCONTROL_MOCK;
});

import { HttpHermesApi, mapPhaseState } from '../api/adapters/httpAdapter';
import { hermesApi, isMockMode, isRealApiMode } from '../api/client';
import { formatElapsed } from '../features/jobs/jobTiming';
import { eventKindColor, isErrorKind } from '../features/events/eventKinds';
import { UNKNOWN } from '../components/DataStates';
import {
  installLiveHermes,
  LIVE_JOB_DETAIL,
  LIVE_JOB_ID,
  LIVE_JOB_SUMMARY
} from './support/liveHermes';

describe('M1 default client mode', () => {
  it('uses HTTP against the local Hermes API when no mock flag is set', () => {
    expect(isMockMode).toBe(false);
    expect(isRealApiMode).toBe(true);
    expect(hermesApi).toBeInstanceOf(HttpHermesApi);
  });
});

describe('M1 HTTP adapter does not invent or swallow data', () => {
  let api: HttpHermesApi;

  beforeEach(() => {
    api = new HttpHermesApi('http://localhost:8000');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('throws when /jobs fails instead of returning zero counts', async () => {
    installLiveHermes({ failJobs: true });
    await expect(api.getTelemetry()).rejects.toThrow('Hermes /jobs returned HTTP 500');
  });

  it('throws when the pipeline cannot be loaded instead of returning an empty pipeline', async () => {
    installLiveHermes({ failJobs: true });
    await expect(api.getPipeline()).rejects.toThrow('HTTP 500');
  });

  it('counts FAILED 24H only for jobs completed inside the last 24 hours', async () => {
    installLiveHermes();
    const telemetry = await api.getTelemetry();
    // The live sample failed on 2026-10-01, outside the window.
    expect(telemetry.failed24hCount).toBe(0);
    expect(telemetry.sampleSize).toBe(1);
    expect(telemetry.tokensToday).toBe(UNKNOWN);
    expect(telemetry.estSpendToday).toBe(UNKNOWN);
    expect(telemetry.sprintBudgetUsedPct).toBeNull();
  });

  it('reports the 24h failure count as unknown when a failed job has no completion time', async () => {
    installLiveHermes({ jobs: [{ ...LIVE_JOB_SUMMARY, completedAt: null }] });
    const telemetry = await api.getTelemetry();
    expect(telemetry.failed24hCount).toBeNull();
  });

  it('counts running work from every active status, not only RUNNING', async () => {
    installLiveHermes({
      jobs: [
        { ...LIVE_JOB_SUMMARY, id: 'j1', status: 'RUNNING' },
        { ...LIVE_JOB_SUMMARY, id: 'j2', status: 'VERIFYING' },
        { ...LIVE_JOB_SUMMARY, id: 'j3', status: 'QUEUED' },
        { ...LIVE_JOB_SUMMARY, id: 'j4', status: 'BLOCKED' }
      ]
    });
    const telemetry = await api.getTelemetry();
    expect(telemetry.runningJobsCount).toBe(2);
    expect(telemetry.queuedJobsCount).toBe(1);
    expect(telemetry.blockedJobsCount).toBe(1);
  });

  it('returns no pipeline when the only job is historical, and does not fetch its detail', async () => {
    const { requests } = installLiveHermes();
    const steps = await api.getPipeline();
    expect(steps).toEqual([]);
    expect(requests).not.toContain(`/jobs/${LIVE_JOB_ID}`);
  });

  it('returns the phases of the active job with its own id', async () => {
    installActiveDetail('job-active');
    const steps = await api.getPipeline();
    expect(steps.map((s) => s.jobId)).toEqual(['job-active', 'job-active']);
    expect(steps.map((s) => s.state)).toEqual(['COMPLETED', 'FAILED']);
  });

  it('keeps FAILED, CANCELLED and SKIPPED distinct from BLOCKED and QUEUED', () => {
    expect(mapPhaseState('FAILED')).toBe('FAILED');
    expect(mapPhaseState('CANCELLED')).toBe('CANCELLED');
    expect(mapPhaseState('SKIPPED')).toBe('SKIPPED');
    expect(mapPhaseState('BLOCKED')).toBe('BLOCKED');
    expect(mapPhaseState('PENDING')).toBe('QUEUED');
    expect(mapPhaseState('SOMETHING_NEW')).toBe('UNKNOWN');
    expect(mapPhaseState(null)).toBe('UNKNOWN');
  });

  it('reports no projection rows, since Hermes has no projection source', async () => {
    expect(await api.getProjections()).toEqual([]);
  });

  it('does not claim a strict human-review or serial policy the API never reported', async () => {
    const settings = await api.getSettings();
    const text = JSON.stringify(settings);
    expect(text).not.toContain('Strict');
    expect(text).not.toContain('Governed Hermes Runtime');
    expect(settings.policy[0].value).toBe('Not exposed by the Hermes API');
  });

  it('shows agent context, token and quota values as unknown, not as zero or a percentage', async () => {
    installLiveHermes();
    const agent = await api.getAgent('claude');
    expect(agent).not.toBeNull();
    expect(agent!.input).toBe(UNKNOWN);
    expect(agent!.inPct).toBe(UNKNOWN);
    expect(agent!.cachePct).toBe(UNKNOWN);
    expect(agent!.allowance).toEqual([]);
    expect(agent!.runs).toEqual([]);
    expect(agent!.reset).toBe(UNKNOWN);
    expect(agent!.traceId).toBeUndefined();
  });

  it('does not invent a capability for an agent that reports none', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => [{ id: 'bare', displayName: 'Bare', provider: 'Local', model: 'm', role: 'r', capabilities: null, status: 'IDLE' }]
    }) as unknown as Response);
    vi.stubGlobal('fetch', fetchMock);
    const [agent] = await api.getAgents();
    expect(agent.capabilities).toEqual([]);
  });
});

describe('M1 derived values', () => {
  it('formats elapsed from the job timestamps for finished and running jobs', () => {
    const now = Date.parse('2026-10-14T12:00:00Z');
    // Finished: fixed duration, independent of the clock.
    expect(formatElapsed('2026-10-01T09:00:00Z', '2026-10-01T10:02:05Z', now)).toBe('1:02:05');
    // Running: measured to now.
    expect(formatElapsed('2026-10-14T11:58:30Z', null, now)).toBe('01:30');
    // Unknown start or impossible ordering is unknown, never a clock value.
    expect(formatElapsed(null, null, now)).toBe(UNKNOWN);
    expect(formatElapsed('2026-10-14T13:00:00Z', null, now)).toBe(UNKNOWN);
  });

  it('treats runtime failure kinds as errors, including the live job and execution kinds', () => {
    for (const kind of ['error', 'retry', 'quota.warn', 'job.failed', 'agent.failed', 'execution.failed', 'execution.release_failed']) {
      expect(isErrorKind(kind)).toBe(true);
    }
    expect(isErrorKind('agent.started')).toBe(false);
    expect(eventKindColor('job.failed')).toBe('#F2555A');
  });
});

/** Serves the job detail for an arbitrary id, used when the active job has its own id. */
function installActiveDetail(jobId: string) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    const body = url.pathname === '/jobs' ? [{ ...LIVE_JOB_SUMMARY, id: jobId, status: 'RUNNING' }] : { ...LIVE_JOB_DETAIL, id: jobId, status: 'RUNNING' };
    return { ok: true, status: 200, statusText: 'OK', json: async () => body } as unknown as Response;
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}
