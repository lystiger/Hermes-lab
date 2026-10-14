import {
  ExecutionBackendStatus,
  ExecutionEventKind,
  ExecutionEventMetadata,
  ExecutionResource,
  ExecutionResourceState,
  ExecutionSnapshot,
  TraceEvent
} from '../api/types';

// Pure reducer for D-009 execution state: GET /execution snapshot as the base, `execution.*` events on top.
// No React or zustand here so the ordering / idempotency rules can be tested directly.

const EXECUTION_PREFIX = 'execution.';
const MAX_APPLIED_IDS = 500;

export interface ExecutionView {
  backends: ExecutionBackendStatus[];
  resources: Record<string, ExecutionResource>;
  openrig: ExecutionSnapshot['openrig'];
  /** Bounded dedupe set of event ids already applied (idempotency). */
  appliedEventIds: string[];
  /** Newest rawTs applied per resource key; older events for that resource are stale and dropped. */
  lastRawTs: Record<string, number>;
  /** The snapshot's takenAt: events at or before it are already in the snapshot and are ignored. */
  snapshotTakenAt: number | null;
}

export const EMPTY_EXECUTION_VIEW: ExecutionView = {
  backends: [],
  resources: {},
  openrig: null,
  appliedEventIds: [],
  lastRawTs: {},
  snapshotTakenAt: null
};

// Snapshot `since` is ISO 8601; event `ts` is a display clock, so derive ISO from rawTs (epoch seconds).
function isoFromRawTs(rawTs: number): string {
  return new Date(rawTs * 1000).toISOString();
}

export function resourceKey(backend: string, kind: string, id: string): string {
  return `${backend}|${kind}|${id}`;
}

export function isExecutionEvent(evt: Pick<TraceEvent, 'kind'>): boolean {
  return evt.kind.startsWith(EXECUTION_PREFIX);
}

export function viewFromSnapshot(snapshot: ExecutionSnapshot): ExecutionView {
  const resources: Record<string, ExecutionResource> = {};
  for (const r of snapshot.resources) {
    resources[resourceKey(r.backend, r.kind, r.id)] = { ...r, details: { ...r.details } };
  }
  return {
    backends: snapshot.backends.map((b) => ({ ...b })),
    resources,
    openrig: snapshot.openrig,
    appliedEventIds: [],
    lastRawTs: {},
    snapshotTakenAt: typeof snapshot.takenAt === 'number' ? snapshot.takenAt : null
  };
}

function findKeyByExecution(resources: Record<string, ExecutionResource>, executionId: string): string | undefined {
  return Object.keys(resources).find((k) => resources[k].executionId === executionId);
}

function detailsFromMetadata(meta: Partial<ExecutionEventMetadata>): Record<string, any> {
  const out: Record<string, any> = {};
  if (meta.reused !== undefined) out.reused = meta.reused;
  if (meta.generation !== undefined) out.generation = meta.generation;
  if (meta.rigId !== undefined) out.rigId = meta.rigId;
  if (meta.sessionName !== undefined) out.sessionName = meta.sessionName;
  if (meta.nodeId !== undefined) out.nodeId = meta.nodeId;
  return out;
}

// Same transitions as Hermes's ExecutionRegistry (D-010 clarification 6), so a refresh never changes
// what a resource means: failed/cancelled executions are releasing their resource, and `failed` is
// reserved for a teardown that failed. `finished` leaves the state unchanged; `released` removes the row.
const LIFECYCLE_STATE: Partial<Record<ExecutionEventKind, ExecutionResourceState>> = {
  'execution.resource_acquired': 'acquiring',
  'execution.resource_ready': 'ready',
  'execution.running': 'running',
  'execution.failed': 'releasing',
  'execution.cancelled': 'releasing',
  'execution.resource_pooled': 'idle',
  'execution.release_failed': 'failed'
};

/**
 * Applies one TraceEvent to the view. Returns the same reference when the event is not an execution
 * event or was already applied. Events older than the newest applied rawTs for their resource are
 * recorded as applied but do not change the resource.
 */
export function reduceExecutionEvent(view: ExecutionView, evt: TraceEvent): ExecutionView {
  if (!isExecutionEvent(evt)) return view;
  if (view.appliedEventIds.includes(evt.id)) return view;

  const kind = evt.kind as ExecutionEventKind;
  const meta = (evt.metadata ?? {}) as Partial<ExecutionEventMetadata>;
  const backend = meta.backend ?? evt.source.id;

  const base: ExecutionView = {
    ...view,
    appliedEventIds: [...view.appliedEventIds, evt.id].slice(-MAX_APPLIED_IDS)
  };

  const key = meta.resource
    ? resourceKey(backend, meta.resource.kind, meta.resource.id)
    : meta.executionId
      ? findKeyByExecution(view.resources, meta.executionId)
      : undefined;

  // Replayed history can be older than the snapshot; with best-effort persistence a missing
  // release event would otherwise resurrect a resource the snapshot shows as gone.
  if (view.snapshotTakenAt !== null && evt.rawTs <= view.snapshotTakenAt) return base;

  if (!key) return base;
  const lastRawTs = view.lastRawTs[key];
  if (lastRawTs !== undefined && evt.rawTs < lastRawTs) return base;

  const resources = { ...view.resources };
  const current = resources[key];
  const nextLastRawTs = { ...view.lastRawTs, [key]: evt.rawTs };

  if (kind === 'execution.resource_released') {
    delete resources[key];
    return { ...base, resources, lastRawTs: nextLastRawTs };
  }

  const nextState = LIFECYCLE_STATE[kind];
  if (nextState && (meta.resource || current)) {
    const next = buildResource(backend, meta, evt, nextState, current);
    if (kind === 'execution.failed' || kind === 'execution.cancelled' || kind === 'execution.release_failed') {
      next.details = {
        ...next.details,
        errorCode: meta.errorCode,
        error: meta.error,
        ...(kind === 'execution.release_failed' ? { releaseFailed: true } : {}),
        ...(kind === 'execution.cancelled' ? { cancelled: true } : {})
      };
    }
    resources[key] = next;
    return { ...base, resources, lastRawTs: nextLastRawTs };
  }

  // execution.started / finished: no resource state change (Hermes keeps the state as is).
  return { ...base, lastRawTs: nextLastRawTs };
}

function buildResource(
  backend: string,
  meta: Partial<ExecutionEventMetadata>,
  evt: TraceEvent,
  state: ExecutionResourceState,
  current?: ExecutionResource
): ExecutionResource {
  const resource = meta.resource ?? { kind: current!.kind, id: current!.id, label: current!.label };
  const pooled = state === 'idle';
  const stateChanged = !current || current.state !== state;
  const retainedDetails = { ...(current?.details ?? {}) };
  // A new attempt must not inherit the previous failure.
  delete retainedDetails.errorCode;
  delete retainedDetails.error;
  delete retainedDetails.releaseFailed;

  return {
    backend,
    kind: resource.kind,
    id: resource.id,
    label: resource.label,
    state,
    // Hermes keeps the last job/task on a pooled seat, so the UI does too.
    jobId: evt.jobId ?? current?.jobId ?? null,
    taskId: evt.taskId ?? current?.taskId ?? null,
    executionId: meta.executionId ?? current?.executionId ?? null,
    since: stateChanged ? isoFromRawTs(evt.rawTs) : current!.since,
    expiresAt: pooled ? (meta.expiresAt ?? null) : null,
    details: { ...retainedDetails, ...detailsFromMetadata(meta) }
  };
}
