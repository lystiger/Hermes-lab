import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import type { RunReview } from '../api/types';

const hooks = vi.hoisted(() => ({ useReviews: vi.fn(), useAgents: vi.fn(() => ({ agents: [] })) }));
vi.mock('../api/hooks', () => hooks);

import { ReviewRoute } from '../routes/review';
import { mapRunReview } from '../api/mapping';

const base = { loading: false, error: null, stale: false, updatedAt: null, refetch: vi.fn() };
const review: RunReview = {
  jobId: 'run_1', goal: 'Add the Live floor\nwith dependency columns', branch: 'job/run_1/integration', repairs: 1,
  tasks: [
    { id: 'build', role: 'builder', agent: 'claude', status: 'SUCCEEDED' },
    { id: 'verify', role: 'verifier', agent: 'codex', status: 'SUPERSEDED' },
    { id: 'recheck_verify_1', role: 'verifier', agent: 'codex', status: 'SUCCEEDED' }
  ],
  verdict: { task: 'recheck_verify_1', summary: 'All checks pass.', findings: ['flaky test reran green'] },
  costUsd: 0.0465, totalTokens: 1_310_000, prUrl: 'https://github.com/o/r/pull/23', finishedAt: '2026-10-22T14:00:00Z'
};

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe('Review page', () => {
  it('explains an empty review list', () => {
    hooks.useReviews.mockReturnValue({ ...base, reviews: [] });
    render(<ReviewRoute />);
    expect(screen.getByText(/No finished runs yet/)).toBeInTheDocument();
  });

  it('shows a finished run with its verdict, cost, task chain and pull request', () => {
    hooks.useReviews.mockReturnValue({ ...base, reviews: [review] });
    render(<ReviewRoute />);
    const card = screen.getByRole('article', { name: 'Add the Live floor' });
    expect(within(card).getByRole('link', { name: 'Open pull request' })).toHaveAttribute('href', review.prUrl);
    expect(within(card).getByText('job/run_1/integration')).toBeInTheDocument();
    expect(within(card).getByText('$0.0465 · 1.31M tokens')).toBeInTheDocument();
    expect(within(card).getByText(/All checks pass/)).toBeInTheDocument();
    expect(within(card).getByText('flaky test reran green')).toBeInTheDocument();
    const tasks = within(within(card).getByRole('list', { name: 'Tasks' })).getAllByRole('listitem');
    expect(tasks).toHaveLength(3);
    expect(tasks[1]).toHaveClass('opacity-60');
  });

  it('says so when a run has no pull request or no verdict', () => {
    hooks.useReviews.mockReturnValue({ ...base, reviews: [{ ...review, prUrl: null, verdict: null }] });
    render(<ReviewRoute />);
    expect(screen.queryByRole('link', { name: 'Open pull request' })).not.toBeInTheDocument();
    expect(screen.getByText('No pull request')).toBeInTheDocument();
    expect(screen.getByText('No verifier verdict was recorded for this run.')).toBeInTheDocument();
  });

  it('shows the load error with a retry when nothing loaded', () => {
    hooks.useReviews.mockReturnValue({ ...base, reviews: [], error: new Error('Hermes /reviews returned HTTP 500') });
    render(<ReviewRoute />);
    expect(screen.getByRole('button', { name: 'retry' })).toBeInTheDocument();
  });
});

describe('review mapping', () => {
  it('maps the Hermes review shape and keeps missing values empty', () => {
    const mapped = mapRunReview({ jobId: 'j', goal: 'g', branch: 'b', repairs: 0, tasks: [], verdict: null, costUsd: null,
                                  totalTokens: 0, prUrl: null, finalizedAt: '2026-10-22T14:00:00Z' });
    expect(mapped).toMatchObject({ jobId: 'j', verdict: null, costUsd: null, prUrl: null, finishedAt: '2026-10-22T14:00:00Z' });
  });
});
