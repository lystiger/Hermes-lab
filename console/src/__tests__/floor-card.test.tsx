import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FloorCard } from '../features/floor/FloorCard';
import type { TimelineRow } from '../features/jobs/runTimeline';

const NOW = Date.parse('2026-10-22T10:00:00Z');

const row = (overrides: Partial<TimelineRow> = {}): TimelineRow => ({
  key: 'p1',
  order: 1,
  name: 'prompts/build.md',
  role: 'builder',
  agentId: 'claude',
  state: 'RUNNING',
  startMs: NOW - 125_000,
  endMs: null,
  ...overrides
});

describe('FloorCard', () => {
  it('shows role, agent initial, running status, elapsed time and latest event', () => {
    render(
      <FloorCard
        row={row()}
        actor={{ id: 'claude', kind: 'agent', displayName: 'Claude', accentColor: '#c8a' }}
        latestEvent="Tests started"
        nowMs={NOW}
      />
    );
    expect(screen.getByText('builder')).toBeTruthy();
    expect(screen.getByText('C')).toBeTruthy();
    expect(screen.getByText('Running')).toBeTruthy();
    expect(screen.getByText('2m 05s')).toBeTruthy();
    expect(screen.getByText('Tests started')).toBeTruthy();
  });

  it('falls back to the phase label when no role is reported and renders no buttons', () => {
    const { container } = render(<FloorCard row={row({ role: undefined, state: 'COMPLETED', endMs: NOW - 5_000 })} nowMs={NOW} />);
    expect(screen.getByText('build')).toBeTruthy();
    expect(screen.getByText('Done')).toBeTruthy();
    expect(screen.getByText('No events yet')).toBeTruthy();
    expect(container.querySelector('button')).toBeNull();
  });
});
