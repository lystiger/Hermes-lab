import { describe, expect, it } from 'vitest';
import { formatResetIn, statusTone } from './format';

describe('formatResetIn', () => {
  it('formats seconds as a short countdown', () => {
    expect(formatResetIn(0)).toBe('now');
    expect(formatResetIn(2700)).toBe('45m');
    expect(formatResetIn(7800)).toBe('2h 10m');
  });
  it('drops empty units and handles days', () => {
    expect(formatResetIn(7200)).toBe('2h');
    expect(formatResetIn(30)).toBe('now');
    expect(formatResetIn(90_000)).toBe('1d 1h');
  });
});

describe('statusTone', () => {
  it('maps each status to its tone', () => {
    expect(statusTone('ok')).toBe('success');
    expect(statusTone('warn')).toBe('warning');
    expect(statusTone('alarm')).toBe('danger');
    expect(statusTone('stale')).toBe('muted');
    expect(statusTone('not ready')).toBe('muted');
  });
});
