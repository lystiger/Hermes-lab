import {
  AgentRun,
  ArtifactRef,
  CapacityTelemetry,
  JobObservation,
  JobTokenTelemetry,
  ProviderTelemetry,
  TaskNode,
  TraceEvent,
  UsageSnapshotView
} from './types';
import { resolveActorPresentation } from './actors';
import { UNKNOWN } from './unknown';

/** Label for every capacity total. These are counted since the runtime process started, never per day. */
export const CAPACITY_WINDOW_LABEL = 'since runtime start (process lifetime, not daily)';

/** First value present under any of the keys. Real null counts as present; only undefined is skipped. */
export function pick(source: any, ...keys: string[]): any {
  if (!source || typeof source !== 'object') return undefined;
  for (const key of keys) {
    if (source[key] !== undefined) return source[key];
  }
  return undefined;
}

function nullableString(value: unknown): string | null {
  return typeof value === 'string' && value !== '' ? value : null;
}

function nullableNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];
}

function artifactRefs(value: unknown): ArtifactRef[] {
  return Array.isArray(value) ? (value as ArtifactRef[]) : [];
}

/** HH:MM:SS.mmm in local time, matching the bus `ts` display format. */
export function formatClock(iso: string | null | undefined): string {
  if (!iso) return UNKNOWN;
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return UNKNOWN;
  const d = new Date(ms);
  const pad = (n: number, w = 2) => String(n).padStart(w, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
}

function epochSeconds(iso: string | null | undefined): number {
  if (!iso) return 0;
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? 0 : ms / 1000;
}

/** Event from the live bus (GET /events, GET /events/stream). */
export function mapBusEvent(dto: any): TraceEvent {
  return {
    id: dto.id,
    ts: dto.ts,
    rawTs: dto.rawTs,
    source: {
      id: dto.source.id,
      kind: dto.source.kind,
      displayName: dto.source.displayName,
      accentColor: dto.source.accentColor || resolveActorPresentation(dto.source.id).accentColor
    },
    kind: dto.kind,
    detail: dto.detail,
    dur: dto.dur || UNKNOWN,
    jobId: nullableString(dto.jobId),
    taskId: nullableString(dto.taskId),
    runId: nullableString(dto.runId),
    actorId: nullableString(dto.actorId),
    metadata: dto.metadata
  };
}

/** Event as persisted in the durable store (GET /jobs/{id}/events, StoredRuntimeEvent.to_dict). */
export function mapStoredEvent(dto: any): TraceEvent {
  const actorId = nullableString(pick(dto, 'actor_id', 'actorId'));
  const kind = String(pick(dto, 'event_type', 'eventType', 'kind') ?? 'unknown');
  const occurredAt = nullableString(pick(dto, 'occurred_at', 'ts'));
  return {
    id: String(pick(dto, 'event_id', 'id')),
    ts: formatClock(occurredAt),
    rawTs: epochSeconds(occurredAt),
    source: actorId
      ? { id: actorId, kind: 'agent', displayName: actorId, accentColor: resolveActorPresentation(actorId).accentColor }
      : { id: 'runtime', kind: 'runtime', displayName: 'Runtime' },
    kind,
    // Same rule as StoredRuntimeEvent.to_dict(): detail, else payload reason, else the event type.
    detail: String(pick(dto, 'detail') ?? pick(pick(dto, 'payload'), 'detail') ?? pick(pick(dto, 'payload'), 'reason') ?? kind),
    dur: UNKNOWN,
    jobId: nullableString(pick(dto, 'job_id', 'jobId')),
    taskId: nullableString(pick(dto, 'task_id', 'taskId')),
    runId: nullableString(pick(dto, 'run_id', 'runId')),
    actorId,
    metadata: pick(dto, 'payload') ?? {}
  };
}

/** Durable envelopes carry event_id/event_type; live bus envelopes carry id/kind and source. */
export function isStoredEvent(dto: any): boolean {
  return dto && typeof dto === 'object' && ('event_type' in dto || 'event_id' in dto);
}

export function mapEvent(dto: any): TraceEvent {
  return isStoredEvent(dto) ? mapStoredEvent(dto) : mapBusEvent(dto);
}

function usageView(raw: any): UsageSnapshotView | null {
  if (!raw || typeof raw !== 'object') return null;
  return {
    source: String(pick(raw, 'source') ?? 'unknown'),
    observedAt: nullableString(pick(raw, 'observed_at', 'observedAt')),
    modelId: nullableString(pick(raw, 'model_id', 'modelId')),
    actorId: nullableString(pick(raw, 'actor_id', 'actorId')),
    inputTokens: nullableNumber(pick(raw, 'input_tokens', 'inputTokens')),
    outputTokens: nullableNumber(pick(raw, 'output_tokens', 'outputTokens')),
    cachedTokens: nullableNumber(pick(raw, 'cached_tokens', 'cachedTokens')),
    tokensUsed: nullableNumber(pick(raw, 'tokens_used', 'tokensUsed')),
    requestsUsed: nullableNumber(pick(raw, 'requests_used', 'requestsUsed')),
    requestsRemaining: nullableNumber(pick(raw, 'requests_remaining', 'requestsRemaining')),
    requestLimit: nullableNumber(pick(raw, 'request_limit', 'requestLimit')),
    tokensRemaining: nullableNumber(pick(raw, 'tokens_remaining', 'tokensRemaining')),
    tokenLimit: nullableNumber(pick(raw, 'token_limit', 'tokenLimit')),
    contextWindow: nullableNumber(pick(raw, 'context_window', 'contextWindow')),
    contextUsed: nullableNumber(pick(raw, 'context_used', 'contextUsed')),
    resetAt: nullableString(pick(raw, 'reset_at', 'resetAt'))
  };
}

function providerTelemetry(providerId: string, raw: any): ProviderTelemetry {
  const totalRequests = nullableNumber(pick(raw, 'total_requests', 'totalRequests')) ?? 0;
  const failures: Record<string, number> = {};
  const breakdown = pick(raw, 'failure_breakdown', 'failureBreakdown');
  if (breakdown && typeof breakdown === 'object') {
    for (const [k, v] of Object.entries(breakdown)) {
      if (typeof v === 'number') failures[k] = v;
    }
  }
  return {
    providerId: String(pick(raw, 'provider_id', 'providerId') ?? providerId),
    status: String(pick(raw, 'status') ?? UNKNOWN),
    statusReason: nullableString(pick(raw, 'status_reason', 'statusReason')),
    totalRequests,
    successCount: nullableNumber(pick(raw, 'success_count', 'successCount')) ?? 0,
    failureCount: nullableNumber(pick(raw, 'failure_count', 'failureCount')) ?? 0,
    // The registry reports 1.0 before any request; that is not a measured rate, so it stays unknown.
    successRate: totalRequests > 0 ? nullableNumber(pick(raw, 'success_rate', 'successRate')) : null,
    throttlingCount: nullableNumber(pick(raw, 'throttling_count', 'throttlingCount')) ?? 0,
    failureBreakdown: failures,
    usage: usageView(pick(raw, 'usage'))
  };
}

/** GET /capacity/telemetry. Missing sections become null, never zero. */
export function mapCapacityTelemetry(raw: any): CapacityTelemetry {
  const s = pick(raw, 'summary');
  const providersRaw = pick(raw, 'providers');
  const providers =
    providersRaw && typeof providersRaw === 'object'
      ? Object.entries(providersRaw).map(([id, p]) => providerTelemetry(id, p))
      : [];
  return {
    timestamp: nullableString(pick(raw, 'timestamp')),
    summary: s && typeof s === 'object'
      ? {
          totalProviders: nullableNumber(pick(s, 'total_providers', 'totalProviders')),
          totalRequests: nullableNumber(pick(s, 'total_requests', 'totalRequests')),
          totalFailures: nullableNumber(pick(s, 'total_failures', 'totalFailures')),
          totalThrottlingEvents: nullableNumber(pick(s, 'total_throttling_events', 'totalThrottlingEvents')),
          totalTokens: nullableNumber(pick(s, 'total_tokens', 'totalTokens')),
          inputTokens: nullableNumber(pick(s, 'input_tokens', 'inputTokens')),
          outputTokens: nullableNumber(pick(s, 'output_tokens', 'outputTokens')),
          cachedTokens: nullableNumber(pick(s, 'cached_tokens', 'cachedTokens'))
        }
      : null,
    providers,
    jobsTracked: nullableNumber(pick(raw, 'jobs_tracked', 'jobsTracked'))
  };
}

/** GET /jobs/{id}/telemetry: `{job_id, tokens: {input_tokens, output_tokens, cached_tokens, total_tokens}}`. */
export function mapJobTokenTelemetry(raw: any, fallbackJobId: string): JobTokenTelemetry {
  const t = pick(raw, 'tokens') ?? {};
  return {
    jobId: String(pick(raw, 'job_id', 'jobId') ?? fallbackJobId),
    inputTokens: nullableNumber(pick(t, 'input_tokens', 'inputTokens')) ?? 0,
    outputTokens: nullableNumber(pick(t, 'output_tokens', 'outputTokens')) ?? 0,
    cachedTokens: nullableNumber(pick(t, 'cached_tokens', 'cachedTokens')) ?? 0,
    totalTokens: nullableNumber(pick(t, 'total_tokens', 'totalTokens')) ?? 0
  };
}

/** TaskNode.to_dict() is camelCase; accept snake keys too. */
export function mapTaskNode(raw: any): TaskNode {
  return {
    taskId: String(pick(raw, 'taskId', 'task_id', 'id') ?? ''),
    jobId: String(pick(raw, 'jobId', 'job_id') ?? ''),
    description: String(pick(raw, 'description') ?? ''),
    status: String(pick(raw, 'status') ?? UNKNOWN),
    dependencies: stringList(pick(raw, 'dependencies')),
    requiredCapabilities: stringList(pick(raw, 'requiredCapabilities', 'required_capabilities')),
    assignedActor: nullableString(pick(raw, 'assignedActor', 'assigned_actor')),
    parentTaskId: nullableString(pick(raw, 'parentTaskId', 'parent_task_id')),
    createdAt: nullableString(pick(raw, 'createdAt', 'created_at')),
    startedAt: nullableString(pick(raw, 'startedAt', 'started_at')),
    completedAt: nullableString(pick(raw, 'completedAt', 'completed_at')),
    attempt: nullableNumber(pick(raw, 'attempt')) ?? 0,
    maxAttempts: nullableNumber(pick(raw, 'maxAttempts', 'max_attempts')),
    error: pick(raw, 'error') ?? null,
    supersededBy: nullableString(pick(raw, 'supersededBy', 'superseded_by')),
    artifactRefs: artifactRefs(pick(raw, 'artifactRefs', 'artifact_refs'))
  };
}

/** AgentRun.to_dict() is snake_case; accept camel keys too. */
export function mapAgentRun(raw: any): AgentRun {
  return {
    runId: String(pick(raw, 'run_id', 'runId', 'id') ?? ''),
    jobId: String(pick(raw, 'job_id', 'jobId') ?? ''),
    taskId: String(pick(raw, 'task_id', 'taskId') ?? ''),
    actorId: String(pick(raw, 'actor_id', 'actorId') ?? ''),
    status: String(pick(raw, 'status') ?? UNKNOWN),
    attempt: nullableNumber(pick(raw, 'attempt')) ?? 1,
    startedAt: nullableString(pick(raw, 'started_at', 'startedAt')),
    finishedAt: nullableString(pick(raw, 'finished_at', 'finishedAt')),
    exitReason: nullableString(pick(raw, 'exit_reason', 'exitReason')),
    error: pick(raw, 'error') ?? null,
    artifactRefs: artifactRefs(pick(raw, 'artifact_refs', 'artifactRefs'))
  };
}

/** Observation.to_dict() is snake_case (runtime/observations.py); accept camel keys too. */
export function mapObservation(raw: any): JobObservation {
  const confidence = pick(raw, 'confidence');
  return {
    observationId: String(pick(raw, 'observation_id', 'observationId', 'id') ?? ''),
    jobId: String(pick(raw, 'job_id', 'jobId') ?? ''),
    kind: String(pick(raw, 'kind') ?? 'discovery'),
    content: String(pick(raw, 'content') ?? ''),
    taskId: nullableString(pick(raw, 'task_id', 'taskId')),
    actorId: nullableString(pick(raw, 'actor_id', 'actorId')),
    source: nullableString(pick(raw, 'source')),
    confidence: nullableNumber(confidence),
    createdAt: nullableString(pick(raw, 'created_at', 'createdAt'))
  };
}

/** Human-readable text for an error payload of unknown shape. */
export function describeError(err: unknown): string {
  if (err === null || err === undefined) return '';
  if (typeof err === 'string') return err;
  if (typeof err === 'object') {
    const e = err as Record<string, unknown>;
    const head = [e.type ?? e.code ?? e.kind, e.message ?? e.reason ?? e.detail].filter((v) => typeof v === 'string' && v);
    if (head.length > 0) return head.join(': ');
    return JSON.stringify(err);
  }
  return String(err);
}
