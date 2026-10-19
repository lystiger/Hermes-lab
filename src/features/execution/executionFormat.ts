import { ExecutionResource, ExecutionResourceState, TraceEvent } from '../../api/types';

export const RESOURCE_STATE_STYLE: Record<ExecutionResourceState, { label: string; color: string }> = {
  acquiring: { label: 'ACQUIRING', color: 'var(--lys-accent-gold)' },
  ready: { label: 'READY', color: 'var(--lys-agent-gemini)' },
  running: { label: 'RUNNING', color: 'var(--lys-status-success)' },
  idle: { label: 'IDLE · POOLED', color: 'var(--lys-text-muted)' },
  releasing: { label: 'RELEASING', color: 'var(--lys-status-warning)' },
  failed: { label: 'FAILED', color: 'var(--lys-status-danger)' }
};

const STATE_ORDER: Record<ExecutionResourceState, number> = {
  failed: 0,
  running: 1,
  acquiring: 2,
  releasing: 3,
  ready: 4,
  idle: 5
};

export function stateStyle(state: string): { label: string; color: string } {
  return (RESOURCE_STATE_STYLE as Record<string, { label: string; color: string }>)[state] ?? {
    label: state.toUpperCase(),
    color: 'var(--lys-text-muted)'
  };
}

export function sortResources(resources: ExecutionResource[]): ExecutionResource[] {
  return [...resources].sort(
    (a, b) => (STATE_ORDER[a.state] ?? 9) - (STATE_ORDER[b.state] ?? 9) || a.label.localeCompare(b.label)
  );
}

/** Groups resources by backend, keeping `backendOrder` first and appending unknown backends. */
export function groupByBackend(
  resources: ExecutionResource[],
  backendOrder: string[]
): Array<{ backend: string; resources: ExecutionResource[] }> {
  const groups = new Map<string, ExecutionResource[]>();
  for (const name of backendOrder) groups.set(name, []);
  for (const r of resources) {
    const list = groups.get(r.backend) ?? [];
    list.push(r);
    groups.set(r.backend, list);
  }
  return [...groups.entries()]
    .filter(([, list]) => list.length > 0)
    .map(([backend, list]) => ({ backend, resources: sortResources(list) }));
}

/** "expires in 09:42" while counting down, "expired" once past. Returns null when there is no expiry. */
export function formatExpiry(expiresAt: string | null, nowMs: number): string | null {
  if (!expiresAt) return null;
  const targetMs = Date.parse(expiresAt);
  if (Number.isNaN(targetMs)) return null;
  const remaining = Math.floor((targetMs - nowMs) / 1000);
  if (remaining <= 0) return 'expired';
  const h = Math.floor(remaining / 3600);
  const m = Math.floor((remaining % 3600) / 60);
  const s = remaining % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `expires in ${h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`}`;
}

export function eventColor(kind: string): string {
  if (kind === 'execution.failed' || kind === 'execution.release_failed') return 'var(--lys-status-danger)';
  if (kind === 'execution.cancelled') return 'var(--lys-status-warning)';
  if (kind === 'execution.running') return 'var(--lys-status-success)';
  if (kind === 'execution.started' || kind === 'execution.resource_acquired' || kind === 'execution.resource_ready') return 'var(--lys-accent-gold)';
  if (kind === 'execution.resource_pooled') return 'var(--lys-text-muted)';
  return 'var(--lys-text-faint)';
}

/** Execution events for the timeline, newest first. */
export function executionTimeline(events: TraceEvent[]): TraceEvent[] {
  return events
    .filter((e) => e.kind.startsWith('execution.'))
    .sort((a, b) => b.rawTs - a.rawTs);
}
