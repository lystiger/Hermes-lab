import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { TraceEvent, ExecutionSnapshot } from '../api/types';
import { hermesApi } from '../api/client';
import { createMockExecutionSnapshot } from '../api/mock/execution';
import {
  EMPTY_EXECUTION_VIEW,
  reduceExecutionEvent,
  resourceKey,
  viewFromSnapshot
} from '../stores/executionReducer';
import { useExecutionStore } from '../stores/useExecutionStore';
import { renderHook, waitFor } from '@testing-library/react';
import { useEventStream } from '../api/hooks';

const SEAT = { kind: 'seat', id: 'seat-reviewer-2', label: 'reviewer-2' };

function evt(
  id: string,
  kind: string,
  rawTs: number,
  metadata: Record<string, any> = {},
  extra: Partial<TraceEvent> = {}
): TraceEvent {
  return {
    id,
    ts: `10:00:${String(Math.floor(rawTs)).padStart(2, '0')}.000`,
    rawTs,
    source: { id: 'openrig', kind: 'runtime', displayName: 'OpenRig' },
    kind,
    detail: kind,
    dur: '—',
    jobId: 'job-142',
    taskId: 'task-142-verify',
    metadata: { backend: 'openrig', executionId: 'exec-1', ...metadata },
    ...extra
  };
}

const SEAT_KEY = resourceKey('openrig', 'seat', 'seat-reviewer-2');

describe('execution reducer (D-009 snapshot + events)', () => {
  it('walks a reused seat through acquire, ready, running and pooling', () => {
    let view = EMPTY_EXECUTION_VIEW;
    view = reduceExecutionEvent(view, evt('e1', 'execution.resource_acquired', 1, { resource: SEAT, reused: true, generation: 'g3' }));
    expect(view.resources[SEAT_KEY].state).toBe('acquiring');
    expect(view.resources[SEAT_KEY].details.reused).toBe(true);

    view = reduceExecutionEvent(view, evt('e2', 'execution.resource_ready', 2, { resource: SEAT }));
    view = reduceExecutionEvent(view, evt('e3', 'execution.running', 3, { resource: SEAT }));
    expect(view.resources[SEAT_KEY].state).toBe('running');
    expect(view.resources[SEAT_KEY].jobId).toBe('job-142');

    view = reduceExecutionEvent(
      view,
      evt('e4', 'execution.resource_pooled', 4, { resource: SEAT, expiresAt: '2030-01-01T00:10:00.000Z' }, { jobId: undefined, taskId: undefined })
    );
    // Like Hermes's registry, a pooled seat keeps the job/task that last held it.
    expect(view.resources[SEAT_KEY]).toMatchObject({
      state: 'idle',
      jobId: 'job-142',
      taskId: 'task-142-verify',
      expiresAt: '2030-01-01T00:10:00.000Z'
    });
  });

  it('drops a stale event that arrives after a newer one for the same resource (ordering)', () => {
    let view = reduceExecutionEvent(EMPTY_EXECUTION_VIEW, evt('e-run', 'execution.running', 12, { resource: SEAT }));
    view = reduceExecutionEvent(view, evt('e-acq', 'execution.resource_acquired', 10, { resource: SEAT }));
    expect(view.resources[SEAT_KEY].state).toBe('running');
  });

  it('is idempotent: re-delivering an applied event returns the same view', () => {
    const first = reduceExecutionEvent(EMPTY_EXECUTION_VIEW, evt('dup', 'execution.resource_acquired', 1, { resource: SEAT }));
    const second = reduceExecutionEvent(first, evt('dup', 'execution.resource_acquired', 1, { resource: SEAT }));
    expect(second).toBe(first);
    expect(Object.keys(second.resources)).toHaveLength(1);
  });

  it('ignores non-execution events without changing the view', () => {
    const agentEvt = evt('a1', 'agent.started', 1, {}, { source: { id: 'claude', kind: 'agent', displayName: 'Claude' } });
    expect(reduceExecutionEvent(EMPTY_EXECUTION_VIEW, agentEvt)).toBe(EMPTY_EXECUTION_VIEW);
  });

  it('marks failures and release failures in red, and removes released resources', () => {
    let view = reduceExecutionEvent(EMPTY_EXECUTION_VIEW, evt('e1', 'execution.resource_acquired', 1, { resource: SEAT }));
    view = reduceExecutionEvent(
      view,
      evt('e2', 'execution.release_failed', 2, { resource: SEAT, errorCode: 'RELEASE_FAILED', error: 'teardown timed out' })
    );
    expect(view.resources[SEAT_KEY]).toMatchObject({ state: 'failed' });
    expect(view.resources[SEAT_KEY].details).toMatchObject({ releaseFailed: true, errorCode: 'RELEASE_FAILED' });

    view = reduceExecutionEvent(view, evt('e3', 'execution.resource_released', 3, { resource: SEAT }));
    expect(view.resources[SEAT_KEY]).toBeUndefined();
  });

  it('resolves a failure without a resource through its executionId', () => {
    let view = reduceExecutionEvent(EMPTY_EXECUTION_VIEW, evt('e1', 'execution.running', 1, { resource: SEAT }));
    view = reduceExecutionEvent(view, evt('e2', 'execution.failed', 2, { errorCode: 'PROTOCOL', error: 'bad frame' }));
    // A backend failure releases the resource; `failed` is reserved for a failed teardown.
    expect(view.resources[SEAT_KEY]).toMatchObject({ state: 'releasing' });
    expect(view.resources[SEAT_KEY].details.errorCode).toBe('PROTOCOL');
  });

  it('matches the Hermes registry for cancel and release failure', () => {
    let view = reduceExecutionEvent(EMPTY_EXECUTION_VIEW, evt('e1', 'execution.running', 1, { resource: SEAT }));
    view = reduceExecutionEvent(view, evt('e2', 'execution.cancelled', 2, { resource: SEAT }));
    expect(view.resources[SEAT_KEY].state).toBe('releasing');
    view = reduceExecutionEvent(view, evt('e3', 'execution.release_failed', 3, { resource: SEAT, errorCode: 'UNAVAILABLE' }));
    expect(view.resources[SEAT_KEY]).toMatchObject({ state: 'failed' });
    expect(view.resources[SEAT_KEY].details.releaseFailed).toBe(true);
  });

  it('a finished execution leaves the resource state unchanged', () => {
    let view = reduceExecutionEvent(EMPTY_EXECUTION_VIEW, evt('e1', 'execution.running', 1, { resource: SEAT }));
    view = reduceExecutionEvent(view, evt('e2', 'execution.finished', 2, { resource: SEAT }));
    expect(view.resources[SEAT_KEY].state).toBe('running');
  });

  it('reconnect reset: a fresh snapshot replaces every previously applied event', () => {
    let view = reduceExecutionEvent(EMPTY_EXECUTION_VIEW, evt('e1', 'execution.resource_acquired', 1, { resource: SEAT }));
    expect(view.appliedEventIds).toEqual(['e1']);

    const snapshot: ExecutionSnapshot = { backends: [], resources: [], openrig: null };
    view = viewFromSnapshot(snapshot);
    expect(view.resources).toEqual({});
    expect(view.appliedEventIds).toEqual([]);
    expect(view.lastRawTs).toEqual({});
  });
});

describe('useExecutionStore (snapshot loading, buffering, reconnect)', () => {
  let getSnapshot: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    useExecutionStore.setState({
      view: EMPTY_EXECUTION_VIEW,
      snapshotStatus: 'idle',
      snapshotError: null,
      snapshotLoadedAt: null,
      latestRequest: 0,
      buffer: null
    });
    getSnapshot = vi.spyOn(hermesApi, 'getExecutionSnapshot');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads the snapshot and reports ready', async () => {
    getSnapshot.mockResolvedValue(createMockExecutionSnapshot());
    await useExecutionStore.getState().refreshSnapshot();

    const state = useExecutionStore.getState();
    expect(state.snapshotStatus).toBe('ready');
    expect(Object.keys(state.view.resources).length).toBeGreaterThan(0);
    expect(state.view.openrig?.ledger.rigIds).toContain('rig-7f3a');
  });

  it('buffers events that arrive during a snapshot request and replays them on top', async () => {
    let resolveSnapshot!: (s: ExecutionSnapshot) => void;
    getSnapshot.mockReturnValue(new Promise<ExecutionSnapshot>((r) => (resolveSnapshot = r)));

    const pending = useExecutionStore.getState().refreshSnapshot();
    useExecutionStore.getState().applyEvent(evt('live-1', 'execution.resource_acquired', 5, { resource: SEAT }));
    expect(useExecutionStore.getState().view.resources[SEAT_KEY]).toBeUndefined();

    resolveSnapshot({ backends: [], resources: [], openrig: null });
    await pending;

    expect(useExecutionStore.getState().view.resources[SEAT_KEY]).toMatchObject({ state: 'acquiring' });
  });

  it('reconnect resync replaces state with the fresh snapshot and drops events it does not contain', async () => {
    getSnapshot.mockResolvedValueOnce({ backends: [], resources: [], openrig: null });
    await useExecutionStore.getState().refreshSnapshot();
    useExecutionStore.getState().applyEvent(evt('before-drop', 'execution.resource_acquired', 7, { resource: SEAT }));
    expect(useExecutionStore.getState().view.resources[SEAT_KEY]).toBeDefined();

    // Stream dropped and reconnected: the stream calls refreshSnapshot, the backend no longer has the seat.
    getSnapshot.mockResolvedValueOnce({ backends: [{ name: 'openrig', available: true, detail: 'ok' }], resources: [], openrig: null });
    await useExecutionStore.getState().refreshSnapshot();

    expect(useExecutionStore.getState().view.resources[SEAT_KEY]).toBeUndefined();
    expect(useExecutionStore.getState().view.backends).toHaveLength(1);
  });

  it('keeps the last good view and reports the error when a refresh fails', async () => {
    getSnapshot.mockResolvedValueOnce(createMockExecutionSnapshot());
    await useExecutionStore.getState().refreshSnapshot();
    const before = Object.keys(useExecutionStore.getState().view.resources).length;

    getSnapshot.mockRejectedValueOnce(new Error('HTTP 503'));
    await useExecutionStore.getState().refreshSnapshot();

    const state = useExecutionStore.getState();
    expect(state.snapshotStatus).toBe('error');
    expect(state.snapshotError).toBe('HTTP 503');
    expect(Object.keys(state.view.resources)).toHaveLength(before);
  });

  it('discards a superseded response so the newest request wins', async () => {
    let resolveFirst!: (s: ExecutionSnapshot) => void;
    getSnapshot
      .mockReturnValueOnce(new Promise<ExecutionSnapshot>((r) => (resolveFirst = r)))
      .mockResolvedValueOnce({ backends: [{ name: 'herdr', available: false, detail: 'down' }], resources: [], openrig: null });

    const first = useExecutionStore.getState().refreshSnapshot();
    await useExecutionStore.getState().refreshSnapshot();
    resolveFirst(createMockExecutionSnapshot());
    await first;

    expect(useExecutionStore.getState().view.backends.map((b) => b.name)).toEqual(['herdr']);
  });
});

describe('snapshot cutoff', () => {
  it('history older than the snapshot never resurrects a resource the snapshot shows as gone', () => {
    let view = viewFromSnapshot({ backends: [], resources: [], openrig: null, takenAt: 10 });
    // Its resource_released event was lost (best-effort persistence); only older history remains.
    view = reduceExecutionEvent(view, evt('old', 'execution.running', 5, { resource: SEAT }));
    expect(view.resources[SEAT_KEY]).toBeUndefined();
    view = reduceExecutionEvent(view, evt('new', 'execution.resource_acquired', 11, { resource: SEAT }));
    expect(view.resources[SEAT_KEY]).toMatchObject({ state: 'acquiring' });
  });
});

describe('useEventStream snapshot -> stream handoff', () => {
  beforeEach(() => {
    useExecutionStore.setState({
      view: EMPTY_EXECUTION_VIEW,
      snapshotStatus: 'idle',
      snapshotError: null,
      snapshotLoadedAt: null,
      latestRequest: 0,
      buffer: null
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('applies execution events that exist only in history (after the snapshot, before the SSE cursor)', async () => {
    vi.spyOn(hermesApi, 'getExecutionSnapshot').mockResolvedValue({ backends: [], resources: [], openrig: null });
    vi.spyOn(hermesApi, 'getHealth').mockResolvedValue({} as any);
    vi.spyOn(hermesApi, 'getTraceEvents').mockResolvedValue([
      evt('h2', 'execution.resource_ready', 2, { resource: SEAT }),
      evt('h1', 'execution.resource_acquired', 1, { resource: SEAT })
    ]);
    vi.spyOn(hermesApi, 'subscribeEvents').mockReturnValue({ unsubscribe: () => {} } as any);

    // Snapshot first (taken before the seat existed), then the stream starts.
    await useExecutionStore.getState().refreshSnapshot();
    const { unmount } = renderHook(() => useEventStream());
    await waitFor(() => expect(useExecutionStore.getState().view.resources[SEAT_KEY]).toMatchObject({ state: 'ready' }));
    unmount();
  });
});
