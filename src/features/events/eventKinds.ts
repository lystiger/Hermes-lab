/**
 * Runtime event taxonomy used by the Errors filter and row colours.
 * Live Hermes kinds include job.failed, agent.failed, execution.failed and execution.release_failed,
 * so failure is matched by suffix rather than by a fixed list of mock-era names.
 */
export function isErrorKind(kind: string): boolean {
  return kind === 'error' || kind === 'retry' || kind === 'quota.warn' || /\.(failed|release_failed)$/.test(kind);
}

export function eventKindColor(kind: string): string {
  if (isErrorKind(kind)) {
    return kind === 'retry' || kind === 'quota.warn' ? '#E3A008' : '#F2555A';
  }
  if (kind.startsWith('agent.')) return '#3FB950';
  if (kind === 'job.start' || kind === 'phase.change') return '#CBA35C';
  return '#8C949F';
}

export type EventCategory = 'failures' | 'warnings' | 'agents' | 'jobs' | 'execution' | 'messages' | 'tools' | 'runtime' | 'other';

export const EVENT_CATEGORIES: { id: EventCategory; label: string; tone: string }[] = [
  { id: 'failures', label: 'Failures', tone: '#F2555A' },
  { id: 'warnings', label: 'Warnings', tone: '#E3A008' },
  { id: 'agents', label: 'Agents', tone: '#3FB950' },
  { id: 'jobs', label: 'Jobs', tone: '#CBA35C' },
  { id: 'execution', label: 'Execution', tone: '#7FB3D5' },
  { id: 'messages', label: 'Messages', tone: '#8C949F' },
  { id: 'tools', label: 'Tools', tone: '#8C949F' },
  { id: 'runtime', label: 'Runtime', tone: '#8C949F' },
  { id: 'other', label: 'Other', tone: '#5C646E' }
];

/** Failure taxonomy for the log: a failure is a failure, a warning is a degraded state, the rest are normal. */
export function eventCategory(kind: string): EventCategory {
  if (isErrorKind(kind) && kind !== 'retry' && kind !== 'quota.warn') return 'failures';
  if (kind === 'retry' || kind === 'quota.warn') return 'warnings';
  if (kind.startsWith('agent.')) return 'agents';
  if (kind.startsWith('job.') || kind.startsWith('phase.')) return 'jobs';
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
  error: '#F2555A',
  warn: '#E3A008',
  ok: '#3FB950',
  info: '#8C949F'
};
