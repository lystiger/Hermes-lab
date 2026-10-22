import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import type { JobPhase } from '../api/types';
import { buildTaskInsights, floorDependencies, formatCost } from '../features/floor/floorInsights';
import { floorColumns } from '../features/floor/floorLayout';
import { FloorCard } from '../features/floor/FloorCard';
import { timelineRows } from '../features/jobs/runTimeline';

const phases: JobPhase[] = [
  { id: 'build', name: 'build', order: 1, role: 'builder', agentId: 'claude', status: 'SUCCEEDED', dependencies: [] },
  { id: 'verify', name: 'verify', order: 2, role: 'verifier', agentId: 'codex', status: 'SUPERSEDED', dependencies: ['build'] },
  { id: 'repair_verify_1', name: 'repair', order: 3, role: 'builder', agentId: 'claude', status: 'SUCCEEDED', dependencies: [] },
  { id: 'recheck_verify_1', name: 'recheck', order: 4, role: 'verifier', agentId: 'codex', status: 'RUNNING', dependencies: ['repair_verify_1'] }
];

const tasks = [
  { task_id: 'build', metadata: { role: 'builder' } },
  { task_id: 'verify', superseded_by: 'recheck_verify_1',
    metadata: { role: 'verifier', verification_summary: '1 test failed', findings: ['m7 test fails', 'copy button', 'retry button', 'extra'] } },
  { task_id: 'repair_verify_1', metadata: { role: 'builder', repair_of: 'verify', findings: ['m7 test fails'] } },
  { task_id: 'recheck_verify_1', metadata: { role: 'verifier', prior_findings: ['m7 test fails'] } }
];

const usage = [
  { taskId: 'repair_verify_1', actorId: 'claude', attempt: 1, status: 'failed', totalTokens: 1000, costUsd: 0.001 },
  { taskId: 'repair_verify_1', actorId: 'claude', attempt: 2, status: 'succeeded', totalTokens: 2000, costUsd: 0.002 },
  { taskId: 'verify', actorId: 'codex', attempt: 1, status: 'failed', totalTokens: 37868, costUsd: null }
];

describe('floor repair chain', () => {
  const insights = buildTaskInsights(tasks, usage);

  it('reads failed check, repair, re-check from left to right', () => {
    const columns = floorColumns(timelineRows({ phases, executionGraph: [] }), floorDependencies(phases, insights));
    expect(columns.map((c) => c.rows.map((r) => r.key))).toEqual([['build'], ['verify'], ['repair_verify_1'], ['recheck_verify_1']]);
  });

  it('sums cost and tokens over every run of a task, and keeps cost unknown when no run reported it', () => {
    expect(insights.get('repair_verify_1')).toMatchObject({ kind: 'repair', cycle: 1, repairOf: 'verify', totalTokens: 3000 });
    expect(insights.get('repair_verify_1')!.costUsd).toBeCloseTo(0.003);
    expect(insights.get('verify')).toMatchObject({ costUsd: null, totalTokens: 37868, supersededBy: 'recheck_verify_1' });
    expect(insights.get('build')).toMatchObject({ costUsd: null, totalTokens: 0, kind: null });
    expect(formatCost(0.0047, 104671)).toBe('$0.0047 · 105k tokens');
    expect(formatCost(null, 12861)).toBe('12.9k tokens');
    expect(formatCost(null, 0)).toBeNull();
  });

  it('shows a replaced check dimmed, with its findings and what replaced it', () => {
    const [, verifyRow] = timelineRows({ phases, executionGraph: [] });
    render(<FloorCard row={verifyRow} insight={insights.get('verify')} nowMs={Date.now()} />);
    const card = screen.getByRole('article', { name: /verifier · Replaced/ });
    expect(card).toHaveClass('opacity-60');
    expect(within(card).getByText('1 test failed')).toBeInTheDocument();
    expect(within(card).getAllByRole('listitem')).toHaveLength(3);
    expect(within(card).getByText('+1 more')).toBeInTheDocument();
    expect(within(card).getByText('Replaced by recheck_verify_1')).toBeInTheDocument();
    expect(within(card).getByText('37.9k tokens')).toBeInTheDocument();
  });

  it('labels repair and re-check cards with their cycle', () => {
    const rows = timelineRows({ phases, executionGraph: [] });
    render(<FloorCard row={rows[2]} insight={insights.get('repair_verify_1')} nowMs={Date.now()} />);
    expect(screen.getByRole('article', { name: /builder · Done · Repair 1/ })).toBeInTheDocument();
    expect(screen.getByText('$0.0030 · 3.0k tokens')).toBeInTheDocument();
  });
});
