import React from 'react';
import { ExternalLink } from 'lucide-react';
import { useAgents, useReviews } from '../api/hooks';
import { resolveActorPresentation } from '../api/actors';
import type { AgentSummary, ReviewTask, ReviewVerdict, RunReview } from '../api/types';
import { EmptyState, ErrorState, LoadingState, StaleNotice } from '../components/DataStates';
import { PageHeader, HeaderCount } from '../components/PageHeader';
import { formatCost } from '../features/floor/floorInsights';
import { formatDateTime } from '../features/time/format';

/**
 * Finished goal-planned runs, newest first. Hermes opens each run's pull request when it completes;
 * this page is where a human reads what was done and checked before merging. It never merges anything.
 */
export const ReviewRoute: React.FC = () => {
  const { reviews, loading, error, stale, updatedAt, refetch } = useReviews();
  const { agents } = useAgents();

  const counts: HeaderCount[] = [
    { label: 'FINISHED RUNS', value: reviews.length },
    { label: 'WITH A PR', value: reviews.filter((r) => r.prUrl).length, tone: 'var(--lys-accent-sky)' }
  ];

  return (
    <div className="flex flex-col min-h-full">
      <PageHeader title="Review" subtitle="Finished runs · merge after reading" counts={counts} updatedAt={updatedAt} />

      <div className="flex-1 flex flex-col gap-4 p-6">
        {stale && <StaleNotice label="Review" error={error} onRetry={refetch} />}
        {loading && reviews.length === 0 && <LoadingState label="Loading finished runs…" />}
        {error && reviews.length === 0 && !loading && <ErrorState label="Review" error={error} onRetry={refetch} />}
        {!loading && !error && reviews.length === 0 && (
          <EmptyState>No finished runs yet. A completed goal run appears here with its pull request.</EmptyState>
        )}
        <ul className="flex flex-col gap-4" aria-label="Finished runs">
          {reviews.map((review) => (
            <li key={review.jobId}>
              <ReviewCard review={review} agents={agents} />
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};

const ReviewCard: React.FC<{ review: RunReview; agents: AgentSummary[] }> = ({ review, agents }) => {
  const [headline, ...rest] = review.goal.split('\n');
  const cost = formatCost(review.costUsd, review.totalTokens);

  return (
    <article aria-label={headline} className="flex flex-col gap-4 p-5 bg-lys-surface-2 border border-lys-subtle">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1 min-w-0 flex-1">
          <h2 title={review.goal} className="text-[14px] font-medium text-lys-primary line-clamp-2">{headline}</h2>
          {rest.length > 0 && <p className="text-[12px] text-lys-muted line-clamp-1">{rest.join(' ')}</p>}
          <dl className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-lys-muted">
            <MetaItem label="Branch"><span className="font-mono-code text-lys-gold truncate" title={review.branch}>{review.branch}</span></MetaItem>
            <MetaItem label="Repairs">
              <span style={review.repairs ? { color: 'var(--lys-status-warning)' } : undefined}>{review.repairs}</span>
            </MetaItem>
            <MetaItem label="Cost"><span className="font-mono-code">{cost ?? 'not reported'}</span></MetaItem>
            <MetaItem label="Finished">{formatDateTime(review.finishedAt ?? undefined)}</MetaItem>
          </dl>
        </div>
        <PullRequestLink url={review.prUrl} />
      </header>

      <VerdictBlock verdict={review.verdict} />
      <TaskChain tasks={review.tasks} agents={agents} />
    </article>
  );
};

const MetaItem: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex items-baseline gap-1 min-w-0">
    <dt className="text-lys-faint">{label}</dt>
    <dd className="min-w-0 flex">{children}</dd>
  </div>
);

/** The run's one action. Without a PR (no remote, gh missing, or turned off) it says so instead of linking. */
const PullRequestLink: React.FC<{ url: string | null }> = ({ url }) =>
  url ? (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-2 px-3 py-2 text-[12px] border border-lys-default text-lys-primary hover:bg-lys-surface-interactive active:scale-95 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 shrink-0"
    >
      Open pull request
      <ExternalLink size={12} aria-hidden="true" />
    </a>
  ) : (
    <span className="text-[12px] text-lys-faint shrink-0" title="Hermes could not open a pull request for this run">No pull request</span>
  );

const VerdictBlock: React.FC<{ verdict: ReviewVerdict | null }> = ({ verdict }) => {
  if (!verdict) {
    return <p className="text-[12px] text-lys-faint">No verifier verdict was recorded for this run.</p>;
  }
  return (
    <section aria-label="Verification" className="flex flex-col gap-1 pl-3 border-l-2" style={{ borderLeftColor: 'var(--lys-status-success)' }}>
      <p className="text-[12px] text-lys-primary">
        <span className="text-lys-success">Verified</span>
        {verdict.summary ? ` · ${verdict.summary}` : ''}
      </p>
      {verdict.findings.length > 0 && (
        <ul className="flex flex-col gap-1">
          {verdict.findings.map((finding) => (
            <li key={finding} className="text-[12px] text-lys-muted">{finding}</li>
          ))}
        </ul>
      )}
      <p className="text-[11px] text-lys-faint truncate" title={verdict.task}>by {verdict.task}</p>
    </section>
  );
};

/** Each task as role and agent, in the order Hermes ran them; replaced checks stay listed but dimmed. */
const TaskChain: React.FC<{ tasks: ReviewTask[]; agents: AgentSummary[] }> = ({ tasks, agents }) => {
  if (tasks.length === 0) return null;
  return (
    <ol aria-label="Tasks" className="flex flex-wrap gap-2">
      {tasks.map((task) => {
        const actor = resolveActorPresentation(task.agent, agents);
        const replaced = task.status.toUpperCase() === 'SUPERSEDED';
        return (
          <li
            key={task.id}
            title={`${task.id} · ${task.status.toLowerCase()}`}
            className={`flex items-center gap-2 px-2 py-1 text-[11px] border border-lys-subtle ${replaced ? 'opacity-60' : ''}`}
          >
            <span className="tracking-wider uppercase text-lys-faint">{task.role}</span>
            <span style={{ color: actor.accentColor }}>{actor.displayName || task.agent}</span>
            {replaced && <span className="text-lys-faint">replaced</span>}
          </li>
        );
      })}
    </ol>
  );
};
