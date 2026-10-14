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
