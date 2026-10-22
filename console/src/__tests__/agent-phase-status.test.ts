import { describe, it, expect, beforeEach } from 'vitest';
import { useConsoleStore } from '../stores/useConsoleStore';
import { TraceEvent } from '../api/types';

function phaseEvent(id: string, rawTs: number, kind: string, agent: string, metadata: Record<string, any> = {}): TraceEvent {
  return {
    id,
    ts: '10:00:00.000',
    rawTs,
    source: { id: agent, kind: 'agent', displayName: agent },
    kind,
    detail: `${kind} for ${agent}`,
    dur: '—',
    jobId: 'job-s08',
    metadata,
  };
}

describe('agent status from sprint phase events', () => {
  beforeEach(() => {
    useConsoleStore.setState({ agentRuntimeStatuses: {}, runningPhases: {}, allEvents: [] });
  });

  it('marks an agent RUNNING on phase.started, with the phase as its current task', () => {
    useConsoleStore.getState().addTraceEvent(phaseEvent('p1', 1, 'phase.started', 'claude', { phase: 'parallel_implementation' }));

    expect(useConsoleStore.getState().agentRuntimeStatuses['claude']).toEqual({
      status: 'RUNNING',
      currentTask: 'parallel_implementation',
    });
  });

  it('keeps several agents RUNNING at the same time', () => {
    const store = useConsoleStore.getState();
    store.addTraceEvent(phaseEvent('p1', 1, 'phase.started', 'claude', { phase: 'backend' }));
    store.addTraceEvent(phaseEvent('p2', 2, 'phase.started', 'codex', { phase: 'frontend' }));

    const statuses = useConsoleStore.getState().agentRuntimeStatuses;
    expect(statuses['claude'].status).toBe('RUNNING');
    expect(statuses['codex'].status).toBe('RUNNING');
  });

  it('marks an agent IDLE on phase.completed and ERROR on phase.failed', () => {
    const store = useConsoleStore.getState();
    store.addTraceEvent(phaseEvent('p1', 1, 'phase.started', 'claude', { phase: 'backend' }));
    store.addTraceEvent(phaseEvent('p2', 2, 'phase.completed', 'claude', { phase: 'backend' }));
    expect(useConsoleStore.getState().agentRuntimeStatuses['claude'].status).toBe('IDLE');

    store.addTraceEvent(phaseEvent('p3', 3, 'phase.started', 'codex', { phase: 'verify' }));
    store.addTraceEvent(phaseEvent('p4', 4, 'phase.failed', 'codex', { phase: 'verify' }));
    expect(useConsoleStore.getState().agentRuntimeStatuses['codex'].status).toBe('ERROR');
  });

  it('ignores phase events whose source is not an agent', () => {
    useConsoleStore.getState().addTraceEvent({
      ...phaseEvent('p1', 1, 'phase.started', 'hermes_runner', { phase: 'x' }),
      source: { id: 'hermes_runner', kind: 'runtime', displayName: 'Hermes Runner' },
    });

    expect(useConsoleStore.getState().agentRuntimeStatuses).toEqual({});
  });

  it('keeps the existing agent.* behaviour', () => {
    useConsoleStore.getState().addTraceEvent(phaseEvent('a1', 1, 'agent.started', 'gemini', { task: 'scaffold' }));
    expect(useConsoleStore.getState().agentRuntimeStatuses['gemini']).toEqual({ status: 'RUNNING', currentTask: 'scaffold' });

    useConsoleStore.getState().addTraceEvent(phaseEvent('a2', 2, 'agent.finished', 'gemini'));
    expect(useConsoleStore.getState().agentRuntimeStatuses['gemini'].status).toBe('IDLE');
  });
});
