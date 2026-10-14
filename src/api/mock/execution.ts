import { ExecutionEventKind, ExecutionResourceRef, ExecutionSnapshot, TraceEvent } from '../types';
import { resolveActorPresentation } from '../actors';

// Mock-only fixtures for the D-009 Execution page. Presented as mock data in the UI (see Execution route banner).

type TsFormatter = (sec: number) => string;

const MOCK_BASE_TS = 10 * 3600 + 42 * 60 + 16;
const MOCK_JOB = '#142';

/** GET /execution fixture. Timestamps are relative to `now` so pooled expiry always reads as a countdown. */
export function createMockExecutionSnapshot(now: number = Date.now()): ExecutionSnapshot {
  const iso = (offsetMs: number) => new Date(now + offsetMs).toISOString();

  return {
    backends: [
      { name: 'subprocess', available: true, detail: 'local process runner · 1 running' },
      { name: 'herdr', available: true, detail: 'pane multiplexer · socket ok' },
      { name: 'openrig', available: true, detail: 'rig daemon reachable · 3 seats in ledger' }
    ],
    resources: [
      {
        backend: 'openrig',
        kind: 'seat',
        id: 'seat-reviewer-2',
        label: 'reviewer-2',
        state: 'running',
        jobId: MOCK_JOB,
        taskId: 'task-142-verify',
        executionId: 'exec-142-verify-2',
        since: iso(-4 * 60_000),
        expiresAt: null,
        details: { reused: true, generation: 'g3', rigId: 'rig-7f3a', sessionName: 'lys-review', nodeId: 'node-2' }
      },
      {
        backend: 'openrig',
        kind: 'seat',
        id: 'seat-builder-1',
        label: 'builder-1',
        state: 'idle',
        jobId: null,
        taskId: null,
        executionId: 'exec-142-build-1',
        since: iso(-9 * 60_000),
        expiresAt: iso(10 * 60_000),
        details: { reused: false, generation: 'g2', rigId: 'rig-7f3a', sessionName: 'lys-build' }
      },
      {
        backend: 'openrig',
        kind: 'seat',
        id: 'seat-codex-1',
        label: 'codex-1',
        state: 'failed',
        jobId: '#139',
        taskId: 'task-139-harden',
        executionId: 'exec-139-harden-1',
        since: iso(-25 * 60_000),
        expiresAt: null,
        details: {
          reused: false,
          generation: 'g1',
          rigId: 'rig-91bc',
          releaseFailed: true,
          errorCode: 'RELEASE_FAILED',
          error: 'teardown timed out; seat kept for retry'
        }
      },
      {
        backend: 'subprocess',
        kind: 'process',
        id: '48213',
        label: 'pytest tests/state -q',
        state: 'running',
        jobId: MOCK_JOB,
        taskId: 'task-142-test',
        executionId: 'exec-142-test-1',
        since: iso(-70_000),
        expiresAt: null,
        details: {}
      },
      {
        backend: 'herdr',
        kind: 'pane',
        id: 'pane-3',
        label: 'gemini build shell',
        state: 'ready',
        jobId: MOCK_JOB,
        taskId: 'task-142-build',
        executionId: 'exec-142-build-0',
        since: iso(-3 * 60_000),
        expiresAt: null,
        details: {}
      }
    ],
    openrig: {
      daemon: 'up',
      ledger: { owners: 3, rigIds: ['rig-7f3a', 'rig-91bc'] }
    }
  };
}

interface EventSpec {
  offset: number; // seconds relative to MOCK_BASE_TS
  backend: string;
  kind: ExecutionEventKind;
  executionId: string;
  jobId?: string;
  taskId?: string;
  resource?: ExecutionResourceRef;
  metadata?: Record<string, any>;
  detail: string;
  idSuffix: string;
}

function buildEvent(spec: EventSpec, fmt: TsFormatter): TraceEvent {
  const rawTs = MOCK_BASE_TS + spec.offset;
  return {
    id: `exec-mock-${spec.idSuffix}`,
    ts: fmt(rawTs),
    rawTs,
    source: resolveActorPresentation(spec.backend),
    kind: spec.kind,
    detail: spec.detail,
    dur: '—',
    jobId: spec.jobId,
    taskId: spec.taskId,
    metadata: {
      backend: spec.backend,
      executionId: spec.executionId,
      ...(spec.resource ? { resource: spec.resource } : {}),
      ...spec.metadata
    }
  };
}

/** Recent execution history used for the timeline and job badges in mock mode. */
export function createMockExecutionHistory(fmt: TsFormatter): TraceEvent[] {
  const specs: EventSpec[] = [
    { offset: -900, backend: 'openrig', kind: 'execution.release_failed', executionId: 'exec-139-harden-1', jobId: '#139', taskId: 'task-139-harden', resource: { kind: 'seat', id: 'seat-codex-1', label: 'codex-1' }, metadata: { errorCode: 'RELEASE_FAILED', error: 'teardown timed out; seat kept for retry', rigId: 'rig-91bc' }, detail: 'codex-1 teardown timed out · kept for retry', idSuffix: 'a1' },
    { offset: -600, backend: 'herdr', kind: 'execution.started', executionId: 'exec-142-build-0', jobId: MOCK_JOB, taskId: 'task-142-build', detail: 'BUILD · herdr pane', idSuffix: 'a2' },
    { offset: -599, backend: 'herdr', kind: 'execution.resource_acquired', executionId: 'exec-142-build-0', jobId: MOCK_JOB, taskId: 'task-142-build', resource: { kind: 'pane', id: 'pane-3', label: 'gemini build shell' }, detail: 'pane-3 acquired', idSuffix: 'a3' },
    { offset: -597, backend: 'herdr', kind: 'execution.running', executionId: 'exec-142-build-0', jobId: MOCK_JOB, taskId: 'task-142-build', resource: { kind: 'pane', id: 'pane-3', label: 'gemini build shell' }, detail: 'BUILD prompt delivered', idSuffix: 'a4' },
    { offset: -300, backend: 'openrig', kind: 'execution.resource_pooled', executionId: 'exec-142-build-1', jobId: MOCK_JOB, taskId: 'task-142-build', resource: { kind: 'seat', id: 'seat-builder-1', label: 'builder-1' }, metadata: { expiresAt: new Date(MOCK_BASE_TS * 1000 + 600_000).toISOString(), rigId: 'rig-7f3a', generation: 'g2' }, detail: 'builder-1 pooled · idle', idSuffix: 'a5' },
    { offset: -240, backend: 'openrig', kind: 'execution.resource_acquired', executionId: 'exec-142-verify-2', jobId: MOCK_JOB, taskId: 'task-142-verify', resource: { kind: 'seat', id: 'seat-reviewer-2', label: 'reviewer-2' }, metadata: { reused: true, generation: 'g3', rigId: 'rig-7f3a', sessionName: 'lys-review' }, detail: 'reviewer-2 acquired · reused', idSuffix: 'a6' },
    { offset: -238, backend: 'openrig', kind: 'execution.resource_ready', executionId: 'exec-142-verify-2', jobId: MOCK_JOB, taskId: 'task-142-verify', resource: { kind: 'seat', id: 'seat-reviewer-2', label: 'reviewer-2' }, metadata: { reused: true, generation: 'g3', rigId: 'rig-7f3a' }, detail: 'reviewer-2 hook-idle', idSuffix: 'a7' },
    { offset: -236, backend: 'openrig', kind: 'execution.running', executionId: 'exec-142-verify-2', jobId: MOCK_JOB, taskId: 'task-142-verify', resource: { kind: 'seat', id: 'seat-reviewer-2', label: 'reviewer-2' }, metadata: { reused: true, generation: 'g3', rigId: 'rig-7f3a' }, detail: 'VERIFY prompt delivered', idSuffix: 'a8' },
    { offset: -70, backend: 'subprocess', kind: 'execution.resource_acquired', executionId: 'exec-142-test-1', jobId: MOCK_JOB, taskId: 'task-142-test', resource: { kind: 'process', id: '48213', label: 'pytest tests/state -q' }, detail: 'pid 48213 spawned', idSuffix: 'a9' },
    { offset: -68, backend: 'subprocess', kind: 'execution.running', executionId: 'exec-142-test-1', jobId: MOCK_JOB, taskId: 'task-142-test', resource: { kind: 'process', id: '48213', label: 'pytest tests/state -q' }, detail: 'pytest tests/state -q', idSuffix: 'a10' }
  ];
  return specs.map((s) => buildEvent(s, fmt));
}

/**
 * Scripted live execution for the mock stream: one subprocess execution per call, emitted in lifecycle order.
 * `seq` makes ids unique across cycles.
 */
export function createMockExecutionScript(seq: number, rawTs: number, fmt: TsFormatter): TraceEvent[] {
  const executionId = `exec-sim-${seq}`;
  const taskId = `task-${MOCK_JOB.slice(1)}-sim-${seq}`;
  const resource: ExecutionResourceRef = { kind: 'process', id: String(50000 + seq), label: `sim task ${seq}` };
  const steps: Array<[ExecutionEventKind, string]> = [
    ['execution.started', `sim task ${seq} started`],
    ['execution.resource_acquired', `pid ${resource.id} spawned`],
    ['execution.resource_ready', `pid ${resource.id} ready`],
    ['execution.running', `sim task ${seq} running`],
    ['execution.finished', `sim task ${seq} exited 0`],
    ['execution.resource_released', `pid ${resource.id} released`]
  ];
  return steps.map(([kind, detail], i) =>
    buildEvent(
      {
        offset: rawTs - MOCK_BASE_TS + i * 0.6,
        backend: 'subprocess',
        kind,
        executionId,
        jobId: MOCK_JOB,
        taskId,
        resource,
        detail,
        idSuffix: `${seq}-${i}`
      },
      fmt
    )
  );
}
