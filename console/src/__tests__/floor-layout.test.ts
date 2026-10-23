import { describe, expect, it } from 'vitest';
import { cardState, floorColumns } from '../features/floor/floorLayout';
import type { TimelineRow } from '../features/jobs/runTimeline';
import type { PipelineStepState } from '../api/types';

const row = (key: string, order: number): TimelineRow => ({
  key, order, name: key, state: 'QUEUED', startMs: null, endMs: null,
});

describe('floor dependency columns', () => {
  it('keeps parallel siblings together and moves dependents after their deepest dependency', () => {
    const build = row('build', 1);
    const api = row('api', 2);
    const ui = row('ui', 3);
    const verify = row('verify', 4);
    const deps = new Map([
      ['api', ['build']], ['ui', ['build']], ['verify', ['build', 'api', 'ui']],
    ]);

    // Input order must not affect dependency resolution or spec order within a column.
    expect(floorColumns([verify, ui, build, api], deps)).toEqual([
      { level: 0, rows: [build] },
      { level: 1, rows: [api, ui] },
      { level: 2, rows: [verify] },
    ]);
  });

  it('falls back to level zero for unknown dependencies while retaining known edges', () => {
    const build = row('build', 1);
    const unknown = row('unknown', 2);
    const mixed = row('mixed', 3);
    expect(floorColumns([mixed, unknown, build], new Map([
      ['unknown', ['missing']], ['mixed', ['missing', 'build']],
    ]))).toEqual([
      { level: 0, rows: [build, unknown] },
      { level: 1, rows: [mixed] },
    ]);
  });

  it('puts phases without dependency information in spec order in one column', () => {
    const first = row('first', 1);
    const second = row('second', 2);
    expect(floorColumns([second, first])).toEqual([{ level: 0, rows: [first, second] }]);
    expect(floorColumns([second, first], new Map([['second', []]])))
      .toEqual([{ level: 0, rows: [first, second] }]);
    expect(floorColumns([])).toEqual([]);
  });

  it('terminates on dependency cycles and preserves every phase', () => {
    const first = row('first', 1);
    const second = row('second', 2);
    const columns = floorColumns([first, second], new Map([
      ['first', ['second']], ['second', ['first']],
    ]));
    expect(columns.flatMap((column) => column.rows).sort((a, b) => a.order - b.order))
      .toEqual([first, second]);
    expect(floorColumns([first], new Map([['first', ['first']]])))
      .toEqual([{ level: 0, rows: [first] }]);
  });
});

describe('floor card states', () => {
  it.each<[PipelineStepState, number | null, string]>([
    ['RUNNING', null, 'running'], ['RUNNING', 0, 'running'],
    ['CLAIMED', null, 'queued'], ['CLAIMED', 0, 'queued'], ['CLAIMED', 1, 'running'],
    ['FAILED', null, 'failed'], ['CANCELLED', 1000, 'failed'],
    ['COMPLETED', 1000, 'done'], ['SKIPPED', null, 'done'],
    ['QUEUED', null, 'queued'], ['BLOCKED', null, 'queued'],
    ['UNKNOWN', null, 'queued'], ['IDLE', null, 'replaced'],
  ])('%s with elapsed %s maps to %s', (state, elapsed, expected) => {
    expect(cardState(state, elapsed)).toBe(expected);
  });
});
