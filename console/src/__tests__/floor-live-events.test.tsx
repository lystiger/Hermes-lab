import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { FloorCard } from '../features/floor/FloorCard';
import { isFailureEvent, latestPhaseEvent } from '../features/floor/floorLayout';
import type { TraceEvent } from '../api/types';

const ev = (id: string, rawTs: number, kind: string, extra: Partial<TraceEvent> = {}): TraceEvent => ({
  id,
  ts: '',
  rawTs,
  source: { id: 'claude', kind: 'agent', displayName: 'Claude' } as TraceEvent['source'],
  kind,
  detail: `${id} detail`,
  dur: '',
  ...extra
});

const build = { key: 'p-build', order: 1 };
const harden = { key: 'p-harden', order: 2 };

afterEach(() => cleanup());

describe('latestPhaseEvent', () => {
  it('matches by phase id and returns the newest of them', () => {
    const events = [
      ev('a', 1, 'phase.started', { jobId: 'job-1', taskId: 'p-build' }),
      ev('b', 3, 'phase.completed', { jobId: 'job-1', metadata: { phaseId: 'p-build' } }),
      ev('c', 2, 'phase.started', { jobId: 'job-1', taskId: 'p-harden' })
    ];
    expect(latestPhaseEvent(build, ['job-1'], events)?.id).toBe('b');
    expect(latestPhaseEvent(harden, ['job-1'], events)?.id).toBe('c');
  });

  it('ignores events from other jobs', () => {
    const events = [ev('a', 1, 'phase.started', { jobId: 'job-2', taskId: 'p-build' })];
    expect(latestPhaseEvent(build, ['job-1'], events)).toBeNull();
  });

  it('falls back to spec order only for phase events that name no phase id', () => {
    const events = [
      ev('a', 1, 'phase.started', { jobId: 'job-1', metadata: { order: 1 } }),
      ev('b', 2, 'execution.running', { jobId: 'job-1', metadata: { order: 1 } })
    ];
    expect(latestPhaseEvent(build, ['job-1'], events)?.id).toBe('a');
  });

  it('does not let a named phase match a different phase by order', () => {
    const events = [ev('a', 1, 'phase.started', { jobId: 'job-1', taskId: 'p-harden', metadata: { order: 1 } })];
    expect(latestPhaseEvent(build, ['job-1'], events)).toBeNull();
  });
});

describe('isFailureEvent', () => {
  it('reads failure kinds', () => {
    expect(isFailureEvent({ kind: 'phase.failed' })).toBe(true);
    expect(isFailureEvent({ kind: 'phase.completed' })).toBe(false);
    expect(isFailureEvent(null)).toBe(false);
  });
});

describe('FloorCard live state', () => {
  const runningCard = { state: 'running' as const, elapsedMs: 1000 };
  const failedCard = { state: 'failed' as const, elapsedMs: 1000 };

  it('shows the latest event detail as the live line', () => {
    render(<FloorCard phase={{ ...build, name: 'build', role: 'builder', startMs: null, endMs: null, state: 'RUNNING' } as never} card={runningCard} agent={null} latestEvent={ev('a', 1, 'phase.started')} liveLine="a detail" />);
    expect(screen.getByText('a detail')).toBeInTheDocument();
  });

  it('highlights a running card only once an event for it exists', () => {
    const phase = { ...build, name: 'build', role: 'builder', startMs: null, endMs: null, state: 'RUNNING' } as never;
    const { unmount } = render(<FloorCard phase={phase} card={runningCard} agent={null} latestEvent={null} liveLine="x" />);
    expect(screen.getByRole('article').className).not.toContain('shadow-[inset');
    unmount();
    render(<FloorCard phase={phase} card={runningCard} agent={null} latestEvent={ev('a', 1, 'phase.started')} liveLine="x" />);
    expect(screen.getByRole('article').className).toContain('shadow-[inset');
  });

  it('colours a failed card red only when its event is a failure', () => {
    const phase = { ...build, name: 'build', role: 'builder', startMs: null, endMs: null, state: 'FAILED' } as never;
    const { unmount } = render(<FloorCard phase={phase} card={failedCard} agent={null} latestEvent={null} liveLine="x" />);
    expect(screen.getByText('Failed').getAttribute('style')).not.toContain('status-danger');
    unmount();
    render(<FloorCard phase={phase} card={failedCard} agent={null} latestEvent={ev('f', 1, 'phase.failed')} liveLine="x" />);
    expect(screen.getByText('Failed').getAttribute('style')).toContain('status-danger');
  });
});
