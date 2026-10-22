import type { TimelineRow } from '../jobs/runTimeline';
import type { PipelineStepState } from '../../api/types';

/**
 * Phase keys mapped to the keys of the phases they depend on. Hermes phases carry no
 * dependency field, so the caller supplies the edges (for example from task dependencies).
 * A phase with no entry, or an empty list, is treated as having no dependencies.
 */
export type PhaseDependencies = ReadonlyMap<string, readonly string[]>;

export interface FloorColumn {
  level: number;
  rows: TimelineRow[];
}

/**
 * Groups phases into dependency levels. Level 0 holds phases with no dependencies; every other
 * phase sits one level after its deepest dependency. Each column is ordered by spec order.
 * Unknown dependency keys are ignored, and a cycle is broken at the edge that closes it so the
 * function always returns.
 */
export function floorColumns(rows: readonly TimelineRow[], deps: PhaseDependencies = new Map()): FloorColumn[] {
  const byKey = new Map(rows.map((r) => [r.key, r]));
  const levels = new Map<string, number>();
  const visiting = new Set<string>();

  const levelOf = (key: string): number => {
    const known = levels.get(key);
    if (known !== undefined) return known;
    // A key already on the stack closes a cycle; treat that edge as absent.
    if (visiting.has(key)) return -1;
    visiting.add(key);
    let level = 0;
    for (const dep of deps.get(key) ?? []) {
      if (!byKey.has(dep)) continue;
      level = Math.max(level, levelOf(dep) + 1);
    }
    visiting.delete(key);
    levels.set(key, level);
    return level;
  };

  const columns = new Map<number, TimelineRow[]>();
  for (const row of rows) {
    const level = levelOf(row.key);
    const column = columns.get(level) ?? [];
    column.push(row);
    columns.set(level, column);
  }

  return [...columns.entries()]
    .sort(([a], [b]) => a - b)
    .map(([level, members]) => ({ level, rows: [...members].sort((a, b) => a.order - b.order) }));
}

/** Visual state of a job card: running, failed, done, or queued. */
export type CardState = 'running' | 'failed' | 'done' | 'queued';

/**
 * Maps a phase state to a card state. A claimed phase counts as running only once it has
 * elapsed time; before that it is still queued. Cancelled phases show as failed (they stopped
 * without finishing), and skipped phases show as done (nothing left to run).
 */
export function cardState(state: PipelineStepState, elapsedMs: number | null): CardState {
  switch (state) {
    case 'RUNNING':
      return 'running';
    case 'CLAIMED':
      return elapsedMs !== null && elapsedMs > 0 ? 'running' : 'queued';
    case 'FAILED':
    case 'CANCELLED':
      return 'failed';
    case 'COMPLETED':
    case 'SKIPPED':
      return 'done';
    default:
      return 'queued';
  }
}
