import type { JobPhase, TaskUsage } from '../../api/types';
import type { PhaseDependencies } from './floorLayout';

/** What the floor adds to a phase card from the job's task records and usage rows. */
export interface TaskInsight {
  /** Id of the check that replaced this one after it found problems. */
  supersededBy: string | null;
  /** Id of the check whose findings this repair task fixes. */
  repairOf: string | null;
  /** Repair cycle this task belongs to (repair_x_2 / recheck_x_2 → 2), when it is part of one. */
  cycle: number | null;
  kind: 'repair' | 'recheck' | null;
  /** The verifier's summary and findings, when this task is a check that reported them. */
  summary: string | null;
  findings: string[];
  /** Cost and tokens summed over every run of this task; costUsd is null when no run reported cost. */
  costUsd: number | null;
  totalTokens: number;
}

const CYCLE = /^(repair|recheck)_.+_(\d+)$/;

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];
}

/**
 * Builds one insight per task from GET /jobs/{id} task records (TaskNode.to_dict) and the job's usage rows.
 * Unknown or missing fields fall back to null or empty, never to invented values.
 */
export function buildTaskInsights(tasks: readonly any[] | undefined, usage: readonly TaskUsage[]): Map<string, TaskInsight> {
  const cost = new Map<string, { costUsd: number | null; totalTokens: number }>();
  for (const row of usage) {
    const prev = cost.get(row.taskId) ?? { costUsd: null, totalTokens: 0 };
    cost.set(row.taskId, {
      costUsd: row.costUsd === null ? prev.costUsd : (prev.costUsd ?? 0) + row.costUsd,
      totalTokens: prev.totalTokens + row.totalTokens
    });
  }

  const insights = new Map<string, TaskInsight>();
  for (const task of tasks ?? []) {
    const id = String(task?.task_id ?? task?.taskId ?? '');
    if (!id) continue;
    const meta = (task?.metadata ?? {}) as Record<string, unknown>;
    const match = CYCLE.exec(id);
    const usageRow = cost.get(id);
    insights.set(id, {
      supersededBy: typeof task?.superseded_by === 'string' ? task.superseded_by : null,
      repairOf: typeof meta.repair_of === 'string' ? meta.repair_of : null,
      cycle: match ? Number(match[2]) : null,
      kind: match ? (match[1] as 'repair' | 'recheck') : null,
      summary: typeof meta.verification_summary === 'string' ? meta.verification_summary : null,
      findings: strings(meta.findings).length ? strings(meta.findings) : strings(meta.prior_findings),
      costUsd: usageRow?.costUsd ?? null,
      totalTokens: usageRow?.totalTokens ?? 0
    });
  }
  return insights;
}

/**
 * Dependency edges for the floor columns: each phase's reported dependencies, plus an edge from a repair
 * to the check it repairs, so the chain reads left to right (failed check → repair → re-check).
 */
export function floorDependencies(phases: readonly JobPhase[] | undefined, insights: ReadonlyMap<string, TaskInsight>): PhaseDependencies {
  const deps = new Map<string, string[]>();
  for (const phase of phases ?? []) {
    const edges = [...(phase.dependencies ?? [])];
    const repairOf = insights.get(phase.id)?.repairOf;
    if (repairOf && !edges.includes(repairOf)) edges.push(repairOf);
    deps.set(phase.id, edges);
  }
  return deps;
}

/** "$0.0047 · 104k tokens", "12.9k tokens" or null when nothing was recorded. */
export function formatCost(costUsd: number | null, totalTokens: number): string | null {
  if (costUsd === null && totalTokens === 0) return null;
  const tokens = totalTokens >= 1000 ? `${(totalTokens / 1000).toFixed(totalTokens >= 100_000 ? 0 : 1)}k` : String(totalTokens);
  return costUsd === null ? `${tokens} tokens` : `$${costUsd.toFixed(4)} · ${tokens} tokens`;
}
