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
}

export const EMPTY_EXECUTION_VIEW: ExecutionView = {
  backends: [],
  resources: {},
  openrig: null,
  appliedEventIds: [],
  lastRawTs: {}
};

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
    lastRawTs: {}
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

const LIFECYCLE_STATE: Partial<Record<ExecutionEventKind, ExecutionResourceState>> = {
  'execution.resource_acquired': 'acquiring',
  'execution.resource_ready': 'ready',
  'execution.running': 'running',
  'execution.resource_pooled': 'idle'
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

  if (kind === 'execution.failed' || kind === 'execution.release_failed') {
    if (!current && !meta.resource) return { ...base, lastRawTs: nextLastRawTs };
    resources[key] = {
      ...(current ?? buildResource(backend, meta, evt, 'failed')),
      state: 'failed',
      since: current?.state === 'failed' ? current.since : evt.ts,
      expiresAt: null,
      details: {
        ...(current?.details ?? {}),
        ...detailsFromMetadata(meta),
        errorCode: meta.errorCode,
        error: meta.error,
        ...(kind === 'execution.release_failed' ? { releaseFailed: true } : {})
      }
    };
    return { ...base, resources, lastRawTs: nextLastRawTs };
  }

  const nextState = LIFECYCLE_STATE[kind];
  if (nextState && meta.resource) {
    const nextResource = buildResource(backend, meta, evt, nextState, current);
    resources[key] = nextResource;
    return { ...base, resources, lastRawTs: nextLastRawTs };
  }

  // execution.started / finished / cancelled: no resource state change. Pooling and release are the
  // events that move the resource out of its job.
  return { ...base, lastRawTs: nextLastRawTs };
}

function buildResource(
  backend: string,
  meta: Partial<ExecutionEventMetadata>,
  evt: TraceEvent,
  state: ExecutionResourceState,
  current?: ExecutionResource
): ExecutionResource {
  const resource = meta.resource!;
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
    jobId: pooled ? null : (evt.jobId ?? current?.jobId ?? null),
    taskId: pooled ? null : (evt.taskId ?? current?.taskId ?? null),
    executionId: meta.executionId ?? current?.executionId ?? null,
    since: stateChanged ? evt.ts : current!.since,
    expiresAt: pooled ? (meta.expiresAt ?? null) : null,
    details: { ...retainedDetails, ...detailsFromMetadata(meta) }
  };
}
