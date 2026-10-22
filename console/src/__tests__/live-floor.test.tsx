import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

vi.mock('../api/hooks', () => ({}));

import { FloorCard } from '../features/floor/FloorCard';
import { floorCardState, floorLevels } from '../features/floor/floorLayout';
import type { FloorCardState, FloorPhase } from '../features/floor/floorLayout';
import type { PipelineStepState, TraceEvent } from '../api/types';

const phase = (key: string, order: number, overrides: Partial<FloorPhase> = {}): FloorPhase => ({
  key, order, name: key, state: 'QUEUED', startMs: null, endMs: null, ...overrides,
});

afterEach(() => cleanup());

describe('floorLevels', () => {
  it('puts parallel hardeners after the builder and the verifier after both hardeners', () => {
    const builder = phase('build', 1, { role: 'builder', state: 'RUNNING' });
    const api = phase('harden-api', 2, { role: 'hardener', dependencies: ['build'] });
    const ui = phase('harden-ui', 3, { role: 'hardener', dependencies: ['build'] });
    const verifier = phase('verify', 4, { role: 'verifier', dependencies: [api.key, ui.key] });

    expect(floorLevels([verifier, ui, builder, api])).toEqual([[builder], [api, ui], [verifier]]);
  });

  it('puts dependency-free phases in column zero in spec order', () => {
    const first = phase('first', 1);
    const second = phase('second', 2, { dependencies: [] });
    expect(floorLevels([second, first])).toEqual([[first, second]]);
    expect(floorLevels([])).toEqual([]);
  });
});

describe('floorCardState', () => {
  it.each<[PipelineStepState, FloorCardState]>([
    ['RUNNING', 'running'], ['CLAIMED', 'running'], ['FAILED', 'failed'],
    ['COMPLETED', 'done'], ['QUEUED', 'queued'], ['BLOCKED', 'queued'],
    ['CANCELLED', 'other'], ['SKIPPED', 'other'], ['UNKNOWN', 'other'], ['IDLE', 'other'],
  ])('maps %s to %s', (state, expected) => {
    expect(floorCardState({ state, startMs: null, endMs: null }, null, 5000))
      .toEqual({ state: expected, elapsedMs: null });
  });

  it('uses a failure event for UNKNOWN without overriding a known state', () => {
    const row = { state: 'UNKNOWN' as const, startMs: null, endMs: null };
    expect(floorCardState(row, { kind: 'phase.FAILED' }, 5000).state).toBe('failed');
    expect(floorCardState(row, { kind: 'phase.started' }, 5000).state).toBe('other');
    expect(floorCardState(row, undefined, 5000).state).toBe('other');
    expect(floorCardState({ ...row, state: 'COMPLETED' }, { kind: 'phase.failed' }, 5000).state).toBe('done');
  });

  it('measures elapsed time until now or the recorded end and clamps negative durations', () => {
    const row = { state: 'RUNNING' as const, startMs: 1000, endMs: null };
    expect(floorCardState(row, null, 5000).elapsedMs).toBe(4000);
    expect(floorCardState({ ...row, endMs: 3000 }, null, 5000).elapsedMs).toBe(2000);
    expect(floorCardState(row, null, 500).elapsedMs).toBe(0);
  });
});

describe('FloorCard', () => {
  it('renders the role, initial mark, status and live line, and updates event highlights', () => {
    const props = {
      phase: phase('harden-api', 2, { role: 'hardener', state: 'RUNNING' }),
      card: { state: 'running' as FloorCardState, elapsedMs: 2000 },
      agent: { id: 'codex', kind: 'agent', displayName: 'Codex' },
      latestEvent: null as TraceEvent | null,
      liveLine: 'Checking API edge cases',
    };
    const event: TraceEvent = {
      id: 'event-1', ts: '', rawTs: 1000, source: props.agent,
      kind: 'phase.started', detail: props.liveLine, dur: '',
    };
    const highlight = 'shadow-[inset_0_0_0_1px_var(--lys-status-success)]';
    const { rerender } = render(<FloorCard {...props} />);
    const article = screen.getByRole('article', { name: 'hardener, Running' });
    expect(screen.getByText('hardener')).toBeInTheDocument();
    expect(screen.getByText('C')).toHaveAttribute('aria-hidden', 'true');
    expect(screen.getByText('Codex')).toBeInTheDocument();
    expect(screen.getByText('Running')).toBeInTheDocument();
    expect(screen.getByText(props.liveLine)).toHaveAttribute('aria-live', 'polite');
    expect(screen.getByText('2s')).toBeInTheDocument();
    expect(article).not.toHaveClass(highlight);

    rerender(<FloorCard {...props} latestEvent={event} />);
    expect(article).toHaveClass(highlight);

    const failedProps = { ...props, card: { state: 'failed' as const, elapsedMs: 2000 } };
    rerender(<FloorCard {...failedProps} latestEvent={event} />);
    expect(article).not.toHaveClass(highlight);
    expect(screen.getByText('Failed').getAttribute('style')).not.toContain('--lys-status-danger');

    rerender(<FloorCard {...failedProps} latestEvent={{ ...event, kind: 'phase.failed' }} />);
    expect(screen.getByRole('article', { name: 'hardener, Failed' })).not.toHaveClass(highlight);
    expect(screen.getByText('Failed').getAttribute('style')).toContain('--lys-status-danger');
    expect(article.querySelector('[aria-hidden="true"][style]')?.getAttribute('style'))
      .toContain('--lys-status-danger');
  });
});
