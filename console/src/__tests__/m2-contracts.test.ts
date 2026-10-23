import { describe, it, expect, vi } from 'vitest';

vi.hoisted(() => {
  delete process.env.VITE_LYSCONTROL_MOCK;
});

import {
  CAPACITY_WINDOW_LABEL,
  describeError,
  formatClock,
  isStoredEvent,
  mapAgentRun,
  mapBusEvent,
  mapCapacityTelemetry,
  mapEvent,
  mapJobTokenTelemetry,
  mapObservation,
  mapStoredEvent,
  mapTaskNode
} from '../api/mapping';
import { mergeJobEvents, explainFailure } from '../features/jobs/jobEvents';
import { mapJobSummary } from '../api/adapters/httpAdapter';
import { LIVE_CAPACITY, LIVE_JOB_DETAIL, LIVE_JOB_SUMMARY, LIVE_JOB_TELEMETRY } from './support/liveHermes';

// Observed live: GET /events?limit=3 (runtime envelope with null job, run and actor).
const OBSERVED_BUS_EVENT = {
  id: 'evt_1791964651140_0001',
  ts: '14:57:31.140',
  rawTs: 1791964651.1409333,
  source: { id: 'hermes', kind: 'runtime', displayName: 'Hermes Runtime', accentColor: '#CBA35C' },
  kind: 'runtime.started',
  detail: 'Hermes Runtime initialized and listening on the event bus',
  dur: '—',
  jobId: null,
  taskId: null,
  runId: null,
  actorId: null,
  metadata: {}
};

// Source-derived: StoredRuntimeEvent.to_dict() (runtime/storage/schema_registry.py).
const STORED_EVENT = {
  event_id: 'evt_store_1',
  id: 'evt_store_1',
  job_id: 'job_1',
  jobId: 'job_1',
  sequence: 4,
  event_type: 'agent.finished',
  eventType: 'agent.finished',
  kind: 'agent.finished',
  occurred_at: '2026-10-14T07:10:00.250000+00:00',
  ts: '2026-10-14T07:10:00.250000+00:00',
  schema_version: 1,
  task_id: 'task_a',
  taskId: 'task_a',
  run_id: 'run_a',
  runId: 'run_a',
  actor_id: 'codex',
  actorId: 'codex',
  parent_event_id: null,
  causation_id: null,
  correlation_id: null,
  payload: { detail: 'verify passed' },
  detail: 'verify passed',
  metadata: { detail: 'verify passed' }
};

describe('M2 event envelopes keep runId and actorId, and real nulls stay null', () => {
  it('maps the observed live bus envelope with null job, task, run and actor', () => {
    const e = mapBusEvent(OBSERVED_BUS_EVENT);
    expect(e.jobId).toBeNull();
    expect(e.runId).toBeNull();
    expect(e.actorId).toBeNull();
    expect(e.source.id).toBe('hermes');
    expect(e.rawTs).toBeCloseTo(1791964651.14, 2);
  });

  it('keeps runId and actorId from a bus event that carries them', () => {
    const e = mapEvent({ ...OBSERVED_BUS_EVENT, id: 'x', jobId: 'job_1', runId: 'run_9', actorId: 'claude' });
    expect(e.runId).toBe('run_9');
    expect(e.actorId).toBe('claude');
  });

  it('normalises the durable stored envelope into the trace shape', () => {
    expect(isStoredEvent(STORED_EVENT)).toBe(true);
    expect(isStoredEvent(OBSERVED_BUS_EVENT)).toBe(false);
    const e = mapEvent(STORED_EVENT);
    expect(e.id).toBe('evt_store_1');
    expect(e.kind).toBe('agent.finished');
    expect(e.jobId).toBe('job_1');
    expect(e.taskId).toBe('task_a');
    expect(e.runId).toBe('run_a');
    expect(e.actorId).toBe('codex');
    expect(e.source).toMatchObject({ id: 'codex', kind: 'agent' });
    expect(e.detail).toBe('verify passed');
    // Stored events have no measured duration; it must not be invented.
    expect(e.dur).toBe('—');
    expect(e.rawTs).toBeCloseTo(Date.parse(STORED_EVENT.occurred_at) / 1000, 3);
  });

  it('gives a stored event with no actor a runtime source, not a made-up agent', () => {
    const e = mapStoredEvent({ ...STORED_EVENT, actor_id: null, actorId: null });
    expect(e.actorId).toBeNull();
    expect(e.source).toEqual({ id: 'runtime', kind: 'runtime', displayName: 'Runtime' });
  });

  it('formats a missing or invalid time as unknown', () => {
    expect(formatClock(null)).toBe('—');
    expect(formatClock('not a date')).toBe('—');
    expect(formatClock(STORED_EVENT.occurred_at)).toMatch(/^\d{2}:\d{2}:\d{2}\.\d{3}$/);
  });
});

describe('M2 capacity telemetry DTO', () => {
  it('maps the observed empty registry without turning absence into a measurement', () => {
    const c = mapCapacityTelemetry(LIVE_CAPACITY);
    expect(c.providers).toEqual([]);
    expect(c.jobsTracked).toBe(0);
    expect(c.summary).toMatchObject({ totalProviders: 0, totalTokens: 0, inputTokens: 0 });
    expect(CAPACITY_WINDOW_LABEL).toContain('since runtime start');
  });

  it('keeps nulls from a populated provider record and derives no rate before any request', () => {
    const c = mapCapacityTelemetry({
      timestamp: '2026-10-14T08:00:00+00:00',
      summary: { total_providers: 1, total_requests: 0, total_tokens: 0 },
      providers: {
        claude: {
          provider_id: 'claude',
          status: 'available',
          status_reason: null,
          total_requests: 0,
          success_count: 0,
          failure_count: 0,
          success_rate: 1.0,
          throttling_count: 0,
          failure_breakdown: {},
          usage: {
            provider_id: 'claude',
            model_id: null,
            actor_id: 'claude',
            input_tokens: 0,
            output_tokens: 0,
            cached_tokens: 0,
            requests_used: 0,
            requests_remaining: null,
            request_limit: null,
            tokens_used: 0,
            tokens_remaining: null,
            token_limit: null,
            context_window: 200000,
            context_used: null,
            reset_at: null,
            observed_at: '2026-10-14T08:00:00+00:00',
            source: 'hermes_estimated'
          }
        }
      },
      jobs_tracked: 0
    });
    const claude = c.providers[0];
    expect(claude.providerId).toBe('claude');
    // The registry's 1.0 before any request is not a measured success rate.
    expect(claude.successRate).toBeNull();
    expect(claude.usage!.source).toBe('hermes_estimated');
    expect(claude.usage!.requestsRemaining).toBeNull();
    expect(claude.usage!.contextUsed).toBeNull();
    expect(claude.usage!.contextWindow).toBe(200000);
    expect(claude.usage!.resetAt).toBeNull();
  });

  it('reports a measured success rate once requests exist', () => {
    const c = mapCapacityTelemetry({
      providers: { gemini: { provider_id: 'gemini', status: 'degraded', total_requests: 4, success_count: 3, failure_count: 1, success_rate: 0.75, throttling_count: 2, failure_breakdown: { http_429: 2, other: 'x' } } }
    });
    expect(c.providers[0].successRate).toBe(0.75);
    expect(c.providers[0].failureBreakdown).toEqual({ http_429: 2 });
    expect(c.summary).toBeNull();
  });
});

describe('M2 job telemetry, tasks, runs and observations', () => {
  it('maps the observed job telemetry shape, including all-zero usage', () => {
    const t = mapJobTokenTelemetry(LIVE_JOB_TELEMETRY, 'fallback');
    expect(t).toEqual({ jobId: LIVE_JOB_TELEMETRY.job_id, inputTokens: 0, outputTokens: 0, cachedTokens: 0, totalTokens: 0, costUsd: null, tasks: [] });
  });

  it('maps a task node from to_dict() camelCase and from snake_case keys, keeping nulls', () => {
    const camel = mapTaskNode({
      taskId: 't1', jobId: 'j1', description: 'write tests', status: 'FAILED', dependencies: ['t0'],
      requiredCapabilities: ['testing'], assignedActor: null, parentTaskId: null,
      createdAt: '2026-10-01T09:00:00Z', startedAt: null, completedAt: null,
      attempt: 2, maxAttempts: 2, error: { type: 'TEST_FAIL', message: 'boom' }, supersededBy: null, artifactRefs: []
    });
    expect(camel.taskId).toBe('t1');
    expect(camel.assignedActor).toBeNull();
    expect(camel.error).toEqual({ type: 'TEST_FAIL', message: 'boom' });
    const snake = mapTaskNode({ task_id: 't2', job_id: 'j1', status: 'PENDING', started_at: null, max_attempts: 2 });
    expect(snake.taskId).toBe('t2');
    expect(snake.maxAttempts).toBe(2);
    expect(snake.error).toBeNull();
  });

  it('maps an AgentRun from its snake_case to_dict() shape', () => {
    const run = mapAgentRun({
      run_id: 'run_1', job_id: 'j1', task_id: 't1', actor_id: 'codex', status: 'timed_out', attempt: 1,
      started_at: '2026-10-01T09:00:00Z', finished_at: null, exit_reason: null, error: null, artifact_refs: [], delegation_decision: null, metadata: {}
    });
    expect(run).toMatchObject({ runId: 'run_1', actorId: 'codex', status: 'timed_out', finishedAt: null, exitReason: null });
  });

  it('maps an Observation from its snake_case to_dict() shape', () => {
    const o = mapObservation({
      observation_id: 'obs_1', job_id: 'j1', kind: 'discovery', content: 'tests import a removed module', task_id: null,
      actor_id: 'claude', source: 'claude', confidence: 0.8, created_at: '2026-10-01T09:01:00Z', metadata: {}
    });
    expect(o).toMatchObject({ observationId: 'obs_1', taskId: null, actorId: 'claude', confidence: 0.8 });
  });

  it('describes error payloads of any shape without losing their text', () => {
    expect(describeError({ type: 'FAILED_TESTS', message: '1 test failed' })).toBe('FAILED_TESTS: 1 test failed');
    expect(describeError('plain')).toBe('plain');
    expect(describeError(null)).toBe('');
    expect(describeError({ foo: 1 })).toBe('{"foo":1}');
  });

  it('maps the job summary with blocked and repair diagnostics preserved', () => {
    const job = mapJobSummary({ ...LIVE_JOB_SUMMARY, blockedReason: 'waiting on review', repairCount: 2, replanCount: 1 });
    expect(job).toMatchObject({ blockedReason: 'waiting on review', repairCount: 2, replanCount: 1, startedAt: LIVE_JOB_SUMMARY.startedAt });
    expect(mapJobSummary(LIVE_JOB_SUMMARY).blockedReason).toBeNull();
  });
});

describe('M2 job trace and failure explanation', () => {
  it('merges durable history and live events without duplicates, newest first', () => {
    const stored = [mapStoredEvent(STORED_EVENT)];
    const live = [mapBusEvent({ ...OBSERVED_BUS_EVENT, id: 'evt_store_1', rawTs: 1, jobId: 'job_1' }), mapBusEvent({ ...OBSERVED_BUS_EVENT, id: 'evt_live_2', rawTs: 9999999999, jobId: 'job_1' })];
    const rows = mergeJobEvents(stored, live);
    expect(rows.map((r) => r.event.id)).toEqual(['evt_live_2', 'evt_store_1']);
    expect(rows.find((r) => r.event.id === 'evt_store_1')!.origin).toBe('stored');
    expect(rows.find((r) => r.event.id === 'evt_live_2')!.origin).toBe('live');
  });

  it('explains a failed job from its own phases, errors and verification', () => {
    const explanation = explainFailure({
      ...(LIVE_JOB_DETAIL as any),
      verification: { status: 'FAILED', results: [] },
      executionGraph: []
    });
    expect(explanation!.headline).toBe('Job failed after 2 phase(s)');
    expect(explanation!.lines).toContain('FAILED_TESTS: 1 test failed');
    expect(explanation!.lines).toContain('phase verify failed');
    expect(explanation!.lines).toContain('verification FAILED');
  });

  it('gives no failure explanation for a running job', () => {
    expect(explainFailure({ ...(LIVE_JOB_DETAIL as any), status: 'RUNNING' })).toBeNull();
  });
});
