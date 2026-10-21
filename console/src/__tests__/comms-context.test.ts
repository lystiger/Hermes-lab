import { describe, expect, it } from 'vitest';
import { contextView, formatTokens, HIGH_SHARE, WARN_SHARE } from '../features/comms/contextUsage';

const usage = (context_tokens: number, context_window: number | null = 1_000_000) => ({
  context_tokens,
  cache_read_tokens: Math.floor(context_tokens / 2),
  cache_creation_tokens: 0,
  output_tokens: 10,
  context_window,
});

describe('chat context meter', () => {
  it('shows nothing until a call has been measured', () => {
    expect(contextView(null)).toBeNull();
    expect(contextView(usage(1000, null))).toBeNull();
  });

  it('stays quiet well below the warning line', () => {
    const view = contextView(usage(120_000))!;
    expect(view.level).toBe('ok');
    expect(view.percent).toBe(12);
    expect(view.label).toContain('120k of 1.0M');
  });

  it('warns from 60% and asks to compact from 85%', () => {
    expect(contextView(usage(WARN_SHARE * 1_000_000))!.level).toBe('warn');
    expect(contextView(usage(HIGH_SHARE * 1_000_000))!.level).toBe('high');
  });

  it('reports how much of the context came from cache', () => {
    expect(contextView(usage(200_000))!.cachePercent).toBe(50);
  });

  it('formats token counts for people', () => {
    expect(formatTokens(950)).toBe('950');
    expect(formatTokens(12_400)).toBe('12k');
    expect(formatTokens(1_000_000)).toBe('1.0M');
  });
});
