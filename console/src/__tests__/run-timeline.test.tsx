import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.hoisted(() => {
  delete process.env.VITE_LYSCONTROL_MOCK;
});

import { render, screen } from '@testing-library/react';
import { HttpHermesApi } from '../api/adapters/httpAdapter';
import { JobPhase, TraceEvent } from '../api/types';
import { JobRunTimeline } from '../features/jobs/JobRunTimeline';
import { timelineRows, timelineWindow } from '../features/jobs/runTimeline';
import { eventCategory, isWarningKind } from '../features/events/eventKinds';
import { useConsoleStore } from '../stores/useConsoleStore';

const T0 = Date.parse('2026-10-22T10:00:00Z');
const iso = (minutes: number) => new Date(T0 + minutes * 60_000).toISOString();

// The shape Hermes returns from GET /jobs/{id}: role per phase, two hardeners in a parallel group.
const PHASES: JobPhase[] = [
  { id: 'phase-4-verify', name: 'verify', order: 4, role: 'verifier', agentId: 'claude', status: 'PENDING' },
  { id: 'phase-1-build', name: 'build', order: 1, role: 'builder', agentId: 'gemini', status: 'SUCCEEDED', startedAt: iso(0), completedAt: iso(5) },
  { id: 'phase-2-harden-api', name: 'harden-api', order: 2, role: 'hardener', agentId: 'claude', status: 'RUNNING', startedAt: iso(5) },
  { id: 'phase-3-harden-ui', name: 'harden-ui', order: 3, role: 'hardener', agentId: 'codex', status: 'SUCCEEDED', startedAt: iso(5), completedAt: iso(9) }
];

describe('run timeline rows', () => {
  it('lists every phase in spec order with its own role, including two phases with the same role', () => {
    const rows = timelineRows({ phases: PHASES, executionGraph: [] });
    expect(rows.map((r) => [r.order, r.role, r.agentId, r.state])).toEqual([
      [1, 'builder', 'gemini', 'COMPLETED'],
      [2, 'hardener', 'claude', 'RUNNING'],
      [3, 'hardener', 'codex', 'COMPLETED'],
      [4, 'verifier', 'claude', 'QUEUED']
    ]);
  });

  it('spans first start to now while a phase is still running, and parallel phases share a start', () => {
    const rows = timelineRows({ phases: PHASES, executionGraph: [] });
    expect(rows[1].startMs).toBe(rows[2].startMs);
    expect(timelineWindow(rows, T0 + 12 * 60_000)).toEqual({ startMs: T0, endMs: T0 + 12 * 60_000 });
  });

  it('has no window when Hermes reported no phase times', () => {
    const rows = timelineRows({ phases: [], executionGraph: [{ id: 's1', phase: 'build', task: 'build', meta: '', state: 'RUNNING', note: 'builder' }] });
    expect(rows[0].role).toBe('builder');
    expect(timelineWindow(rows, Date.now())).toBeNull();
  });

  it('renders one row per phase labelled with role, phase and agent', () => {
    render(<JobRunTimeline job={{ phases: PHASES, executionGraph: [] }} />);
    const rows = screen.getAllByRole('listitem');
    expect(rows).toHaveLength(4);
    expect(rows[1]).toHaveAccessibleName(/^hardener · harden-api · claude · running/i);
    expect(rows[2]).toHaveAccessibleName(/^hardener · harden-ui · codex · completed · 4m 00s/i);
    expect(rows[3]).toHaveAccessibleName(/^verifier · verify · claude · queued$/i);
  });
});

describe('execution order covers every active job', () => {
  afterEach(() => vi.restoreAllMocks());

  it('returns the steps of all active jobs, each with its own job id', async () => {
    const api = new HttpHermesApi('http://localhost:8000');
    vi.spyOn(api, 'getJobs').mockResolvedValue([
      { id: 'a', title: 'A', repository: 'r', status: 'RUNNING', assignedAgentIds: [] },
      { id: 'b', title: 'B', repository: 'r', status: 'COMPLETED', assignedAgentIds: [] },
      { id: 'c', title: 'C', repository: 'r', status: 'VERIFYING', assignedAgentIds: [] }
    ]);
    vi.spyOn(api, 'getJob').mockImplementation(async (id) => ({
      id, title: id, repository: 'r', status: 'RUNNING', assignedAgentIds: [],
      executionGraph: [{ id: `${id}-1`, phase: 'build', task: 'build', meta: '', state: 'RUNNING' }]
    }));
    const steps = await api.getPipeline();
    expect(steps.map((s) => s.jobId)).toEqual(['a', 'c']);
  });
});

function ev(id: string, kind: string, agent: string, metadata: Record<string, any> = {}): TraceEvent {
  return { id, ts: '', rawTs: Number(id.replace(/\D/g, '')), source: { id: agent, kind: 'agent', displayName: agent }, kind, detail: '', dur: '', jobId: 'job-1', metadata };
}

describe('agent status follows the same rules as Hermes GET /agents', () => {
  beforeEach(() => useConsoleStore.setState({ agentRuntimeStatuses: {}, runningPhases: {}, allEvents: [] }));
  const status = (id: string) => useConsoleStore.getState().agentRuntimeStatuses[id];

  it('keeps an agent RUNNING until every parallel phase it runs has finished', () => {
    const add = useConsoleStore.getState().addTraceEvent;
    add(ev('e1', 'phase.started', 'claude', { phase: 'harden-api', order: 2 }));
    add(ev('e2', 'phase.started', 'claude', { phase: 'harden-ui', order: 3 }));
    add(ev('e3', 'phase.completed', 'claude', { phase: 'harden-api', order: 2 }));
    expect(status('claude')).toEqual({ status: 'RUNNING', currentTask: 'harden-ui' });
    add(ev('e4', 'agent.finished', 'claude'));
    expect(status('claude').status).toBe('RUNNING');
    add(ev('e5', 'phase.completed', 'claude', { phase: 'harden-ui', order: 3 }));
    expect(status('claude').status).toBe('IDLE');
  });

  it('treats agent.timed_out as an error and agent.cancelled as idle', () => {
    const add = useConsoleStore.getState().addTraceEvent;
    add(ev('e1', 'agent.started', 'codex'));
    add(ev('e2', 'agent.timed_out', 'codex'));
    expect(status('codex').status).toBe('ERROR');
    add(ev('e3', 'phase.started', 'gemini', { phase: 'build', order: 1 }));
    add(ev('e4', 'agent.cancelled', 'gemini'));
    expect(status('gemini').status).toBe('IDLE');
  });

  it('does not reduce a duplicate event twice', () => {
    const add = useConsoleStore.getState().addTraceEvent;
    add(ev('e1', 'phase.started', 'claude', { phase: 'a', order: 1 }));
    add(ev('e2', 'phase.completed', 'claude', { phase: 'a', order: 1 }));
    add(ev('e1', 'phase.started', 'claude', { phase: 'a', order: 1 }));
    expect(status('claude').status).toBe('IDLE');
  });
});

describe('event taxonomy uses the kinds Hermes emits', () => {
  it('classifies Hermes degraded-state kinds as warnings and task events as jobs', () => {
    for (const kind of ['provider.rate_limited', 'provider.quota_exhausted', 'job.waiting_for_capacity', 'circuit.opened', 'job.blocked']) {
      expect(isWarningKind(kind)).toBe(true);
      expect(eventCategory(kind)).toBe('warnings');
    }
    expect(eventCategory('agent.timed_out')).toBe('failures');
    expect(eventCategory('task.started')).toBe('jobs');
  });
});
