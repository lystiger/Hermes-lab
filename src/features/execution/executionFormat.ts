import { ExecutionResource, ExecutionResourceState, TraceEvent } from '../../api/types';

export const RESOURCE_STATE_STYLE: Record<ExecutionResourceState, { label: string; color: string }> = {
  acquiring: { label: 'ACQUIRING', color: '#CBA35C' },
  ready: { label: 'READY', color: '#5B8CFF' },
  running: { label: 'RUNNING', color: '#3FB950' },
  idle: { label: 'IDLE · POOLED', color: '#8C949F' },
  releasing: { label: 'RELEASING', color: '#E3A008' },
  failed: { label: 'FAILED', color: '#F2555A' }
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
    color: '#8C949F'
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
  if (kind === 'execution.failed' || kind === 'execution.release_failed') return '#F2555A';
  if (kind === 'execution.cancelled') return '#E3A008';
  if (kind === 'execution.running') return '#3FB950';
  if (kind === 'execution.started' || kind === 'execution.resource_acquired' || kind === 'execution.resource_ready') return '#CBA35C';
  if (kind === 'execution.resource_pooled') return '#8C949F';
  return '#5C646E';
}

/** Execution events for the timeline, newest first. */
export function executionTimeline(events: TraceEvent[]): TraceEvent[] {
  return events
    .filter((e) => e.kind.startsWith('execution.'))
    .sort((a, b) => b.rawTs - a.rawTs);
}
