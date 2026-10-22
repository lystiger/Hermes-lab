import type { Job, RunReview } from '../../api/types';

/** What kind of attention an item needs; drives its color and its sort order. */
export type AttentionKind = 'failed' | 'blocked' | 'waiting' | 'review';

export interface AttentionItem {
  key: string;
  kind: AttentionKind;
  title: string;
  /** One line on why it needs you. */
  reason: string;
  /** Where to act: a job to open in the job inspector, a console route, or the PR on GitHub. */
  action: { type: 'job'; jobId: string } | { type: 'route'; to: string } | { type: 'external'; url: string };
}

const ORDER: Record<AttentionKind, number> = { failed: 0, blocked: 1, waiting: 2, review: 3 };
const DAY_MS = 24 * 60 * 60 * 1000;

function reasonText(value: unknown, fallback: string): string {
  if (typeof value === 'string' && value.trim()) return value.trim();
  if (value && typeof value === 'object' && 'message' in value && typeof (value as { message: unknown }).message === 'string') {
    return (value as { message: string }).message;
  }
  return fallback;
}

/**
 * Everything that needs the operator, most urgent first: jobs that failed in the last 24 hours, blocked jobs,
 * jobs paused for provider capacity, and finished runs whose pull request is still open.
 */
export function attentionItems(jobs: readonly Job[], reviews: readonly RunReview[], nowMs: number): AttentionItem[] {
  const items: AttentionItem[] = [];
  for (const job of jobs) {
    const title = job.title || job.id;
    if (job.status === 'FAILED') {
      const done = job.completedAt ? Date.parse(job.completedAt) : NaN;
      if (Number.isNaN(done) || nowMs - done > DAY_MS) continue;
      items.push({ key: `failed:${job.id}`, kind: 'failed', title, reason: reasonText(job.blockedReason, 'The run failed.'),
                   action: { type: 'job', jobId: job.id } });
    } else if (job.status === 'BLOCKED') {
      items.push({ key: `blocked:${job.id}`, kind: 'blocked', title, reason: reasonText(job.blockedReason, 'Blocked; no reason reported.'),
                   action: { type: 'job', jobId: job.id } });
    } else if (job.status === 'WAITING_FOR_CAPACITY') {
      items.push({ key: `waiting:${job.id}`, kind: 'waiting', title,
                   reason: reasonText(job.blockedReason, 'Paused until an agent usage limit resets.'), action: { type: 'route', to: '/floor' } });
    }
  }
  for (const review of reviews) {
    if (review.prState !== 'OPEN' || !review.prUrl) continue;
    items.push({ key: `review:${review.jobId}`, kind: 'review', title: review.goal.split('\n')[0],
                 reason: review.repairs ? `Verified after ${review.repairs} repair cycle${review.repairs === 1 ? '' : 's'}.` : 'Verified.',
                 action: { type: 'external', url: review.prUrl } });
  }
  return items.sort((a, b) => ORDER[a.kind] - ORDER[b.kind]);
}
