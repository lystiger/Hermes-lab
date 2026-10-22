import { describe, expect, it } from 'vitest';
import type { Job, RunReview } from '../api/types';
import { attentionItems } from '../features/overview/attention';

const NOW = Date.parse('2026-10-23T10:00:00Z');
const job = (id: string, status: string, extra: Partial<Job> = {}): Job =>
  ({ id, title: `Job ${id}`, repository: 'r', status, assignedAgentIds: [], ...extra }) as Job;
const review = (jobId: string, prState: RunReview['prState'], repairs = 0): RunReview => ({
  jobId, goal: `Goal ${jobId}\nmore`, branch: 'b', repairs, tasks: [], verdict: null, costUsd: null, totalTokens: 0,
  prUrl: `https://x/pull/${jobId}`, prState, finishedAt: null
});

describe('attention items', () => {
  const items = attentionItems(
    [
      job('ok', 'RUNNING'),
      job('blocked', 'BLOCKED', { blockedReason: 'Verification failed after 3 repair cycles' }),
      job('paused', 'WAITING_FOR_CAPACITY'),
      job('failed-new', 'FAILED', { completedAt: '2026-10-23T08:00:00Z' }),
      job('failed-old', 'FAILED', { completedAt: '2026-10-20T08:00:00Z' })
    ],
    [review('open', 'OPEN', 1), review('merged', 'MERGED'), review('closed', 'CLOSED')],
    NOW
  );

  it('lists failed, blocked, paused and open reviews, most urgent first', () => {
    expect(items.map((i) => i.key)).toEqual(['failed:failed-new', 'blocked:blocked', 'waiting:paused', 'review:open']);
  });

  it('leaves out failures older than 24 hours and reviews that are merged or closed', () => {
    expect(items.some((i) => i.key.includes('failed-old') || i.key.includes('merged') || i.key.includes('closed'))).toBe(false);
  });

  it('gives each item one way to act and a one-line reason', () => {
    const byKey = Object.fromEntries(items.map((i) => [i.key, i]));
    expect(byKey['blocked:blocked']).toMatchObject({ reason: 'Verification failed after 3 repair cycles', action: { type: 'job', jobId: 'blocked' } });
    expect(byKey['waiting:paused'].action).toEqual({ type: 'route', to: '/floor' });
    expect(byKey['review:open']).toMatchObject({ title: 'Goal open', reason: 'Verified after 1 repair cycle.',
                                                 action: { type: 'external', url: 'https://x/pull/open' } });
  });
});
