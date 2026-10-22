/**
 * Runtime event taxonomy used by the Errors filter and row colours.
 * Live Hermes kinds include job.failed, agent.failed, execution.failed and execution.release_failed,
 * so failure is matched by suffix rather than by a fixed list of mock-era names.
 */
export function isErrorKind(kind: string): boolean {
  return kind === 'error' || isWarningKind(kind) || /\.(failed|release_failed|timed_out)$/.test(kind);
}

/** Degraded but not failed: Hermes kinds for limits, capacity, circuit breakers and rerouting. */
const WARNING_KINDS = new Set([
  'retry',
  'quota.warn',
  'provider.rate_limited',
  'provider.quota_exhausted',
  'job.waiting_for_capacity',
  'job.blocked',
  'verification.blocked',
  'circuit.opened',
  'task.rerouted',
  'conversation.limit_reached',
  'delegation.limit_reached'
]);

export function isWarningKind(kind: string): boolean {
  return WARNING_KINDS.has(kind);
}

export function eventKindColor(kind: string): string {
  if (isErrorKind(kind)) {
    return isWarningKind(kind) ? 'var(--lys-status-warning)' : 'var(--lys-status-danger)';
  }
  if (kind.startsWith('agent.')) return 'var(--lys-status-success)';
  if (kind.startsWith('job.') || kind.startsWith('phase.')) return 'var(--lys-accent-gold)';
  return 'var(--lys-text-muted)';
}

export type EventCategory = 'failures' | 'warnings' | 'agents' | 'jobs' | 'execution' | 'messages' | 'tools' | 'runtime' | 'other';

export const EVENT_CATEGORIES: { id: EventCategory; label: string; tone: string }[] = [
  { id: 'failures', label: 'Failures', tone: 'var(--lys-status-danger)' },
  { id: 'warnings', label: 'Warnings', tone: 'var(--lys-status-warning)' },
  { id: 'agents', label: 'Agents', tone: 'var(--lys-status-success)' },
  { id: 'jobs', label: 'Jobs', tone: 'var(--lys-accent-gold)' },
  { id: 'execution', label: 'Execution', tone: 'var(--lys-accent-sky)' },
  { id: 'messages', label: 'Messages', tone: 'var(--lys-text-muted)' },
  { id: 'tools', label: 'Tools', tone: 'var(--lys-text-muted)' },
  { id: 'runtime', label: 'Runtime', tone: 'var(--lys-text-muted)' },
  { id: 'other', label: 'Other', tone: 'var(--lys-text-faint)' }
];

/** Failure taxonomy for the log: a failure is a failure, a warning is a degraded state, the rest are normal. */
export function eventCategory(kind: string): EventCategory {
  if (isWarningKind(kind)) return 'warnings';
  if (isErrorKind(kind)) return 'failures';
  if (kind.startsWith('agent.')) return 'agents';
  if (kind.startsWith('job.') || kind.startsWith('phase.') || kind.startsWith('task.')) return 'jobs';
  if (kind.startsWith('execution.')) return 'execution';
  if (kind.startsWith('message.') || kind.startsWith('thread.') || kind.startsWith('artifact.')) return 'messages';
  if (kind.startsWith('tool.')) return 'tools';
  if (kind.startsWith('runtime.')) return 'runtime';
  return 'other';
}

export type EventSeverity = 'error' | 'warn' | 'ok' | 'info';

export function eventSeverity(kind: string): EventSeverity {
  const category = eventCategory(kind);
  if (category === 'failures') return 'error';
  if (category === 'warnings') return 'warn';
  if (/\.(finished|succeeded|completed|started|ready|acquired|released)$/.test(kind)) return 'ok';
  return 'info';
}

export const SEVERITY_COLOR: Record<EventSeverity, string> = {
  error: 'var(--lys-status-danger)',
  warn: 'var(--lys-status-warning)',
  ok: 'var(--lys-status-success)',
  info: 'var(--lys-text-muted)'
};
