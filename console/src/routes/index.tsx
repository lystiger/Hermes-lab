import React, { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink } from 'lucide-react';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useAgents, useCapacityTelemetry, useJobs, useReviews, useTelemetry } from '../api/hooks';
import { ACTIVE_JOB_STATUSES } from '../api/adapters/httpAdapter';
import type { AgentSummary, Job } from '../api/types';
import { ErrorState, LoadingState, EmptyState, StaleNotice, UNKNOWN, Freshness } from '../components/DataStates';
import { Card } from '../components/Card';
import { PageHeader, HeaderCount } from '../components/PageHeader';
import { useNow } from '../features/execution/useNow';
import { formatElapsed } from '../features/jobs/jobTiming';
import { attentionItems, type AttentionItem, type AttentionKind } from '../features/overview/attention';

const KIND_LABEL: Record<AttentionKind, string> = { failed: 'Failed', blocked: 'Blocked', waiting: 'Paused', review: 'Review' };
const KIND_COLOR: Record<AttentionKind, string> = {
  failed: 'var(--lys-status-danger)',
  blocked: 'var(--lys-status-warning)',
  waiting: 'var(--lys-status-warning)',
  review: 'var(--lys-accent-sky)'
};

/** Jobs still in progress, including those paused until an agent usage limit resets. */
const IN_PROGRESS = new Set<string>([...ACTIVE_JOB_STATUSES, 'WAITING_FOR_CAPACITY']);

/**
 * What needs the operator: failed, blocked and paused runs and open pull requests first, then what is running
 * and the agents. Details live on the Floor (runs), Review (finished runs), Queue (backlog) and Events (log).
 */
export const OverviewRoute: React.FC = () => {
  const { jobs, loading: jobsLoading, error: jobsError, stale: jobsStale, refetch: refetchJobs, updatedAt } = useJobs();
  const { reviews } = useReviews();
  const { telemetry, error: telemetryError, refetch: refetchTelemetry } = useTelemetry();
  const { capacity } = useCapacityTelemetry();
  const processTokens = capacity?.summary?.totalTokens;
  const nowMs = useNow(1000);

  const items = useMemo(() => attentionItems(jobs, reviews, nowMs), [jobs, reviews, nowMs]);
  const running = useMemo(() => jobs.filter((j) => IN_PROGRESS.has(j.status)), [jobs]);
  const openReviews = reviews.filter((r) => r.prState === 'OPEN').length;

  const counts: HeaderCount[] = telemetry
    ? [
        { label: 'RUNNING', value: telemetry.runningJobsCount, tone: 'var(--lys-status-success)' },
        { label: 'QUEUED', value: telemetry.queuedJobsCount },
        { label: 'BLOCKED', value: telemetry.blockedJobsCount, tone: telemetry.blockedJobsCount ? 'var(--lys-status-warning)' : undefined },
        {
          label: 'FAILED 24H',
          value: telemetry.failed24hCount ?? UNKNOWN,
          tone: telemetry.failed24hCount ? 'var(--lys-status-danger)' : undefined,
          title: telemetry.failed24hCount === null ? 'A failed job has no completion time, so the 24h window cannot be applied' : undefined
        },
        {
          label: 'TOKENS',
          value: typeof processTokens === 'number' ? processTokens : UNKNOWN,
          unit: 'tok',
          title: 'Since runtime start'
        },
        { label: 'TO REVIEW', value: openReviews, tone: openReviews ? 'var(--lys-accent-sky)' : undefined, title: 'Finished runs whose pull request is open' }
      ]
    : [];

  return (
    <div className="flex flex-col min-h-full">
      <PageHeader updatedAt={updatedAt} title="Overview" subtitle="What needs you" counts={counts} />

      <div className="flex-1 flex flex-col gap-6 p-6 max-w-5xl w-full">
        {telemetryError && !telemetry && <ErrorState label="Metrics" error={telemetryError} onRetry={refetchTelemetry} />}
        {jobsStale && <StaleNotice label="Job queue" error={jobsError} onRetry={refetchJobs} />}
        {jobsLoading && jobs.length === 0 ? (
          <Card><LoadingState label="Loading jobs…" /></Card>
        ) : jobsError && jobs.length === 0 ? (
          <Card><ErrorState label="Job queue" error={jobsError} onRetry={refetchJobs} /></Card>
        ) : (
          <>
            <AttentionList items={items} />
            <RunningNow jobs={running} nowMs={nowMs} />
          </>
        )}
        <AgentsSummary />
      </div>
    </div>
  );
};

const AttentionList: React.FC<{ items: AttentionItem[] }> = ({ items }) => (
  <section aria-label="Needs you" className="flex flex-col gap-3">
    <h2 className="text-[11px] font-medium tracking-wider uppercase text-lys-faint">Needs you · {items.length}</h2>
    {items.length === 0 ? (
      <EmptyState>Nothing needs you right now.</EmptyState>
    ) : (
      <ul className="flex flex-col gap-2">
        {items.map((item) => (
          <li key={item.key}>
            <AttentionRow item={item} />
          </li>
        ))}
      </ul>
    )}
  </section>
);

const AttentionRow: React.FC<{ item: AttentionItem }> = ({ item }) => {
  const color = KIND_COLOR[item.kind];
  return (
    <div className="flex items-center gap-4 p-3 bg-lys-surface-2 border-l-2" style={{ borderLeftColor: color }}>
      <span style={{ color }} className="w-16 shrink-0 text-[11px] font-medium tracking-wider uppercase">{KIND_LABEL[item.kind]}</span>
      <div className="flex flex-col gap-1 min-w-0 flex-1">
        <span title={item.title} className="text-[13px] text-lys-primary truncate">{item.title}</span>
        <span title={item.reason} className="text-[12px] text-lys-muted truncate">{item.reason}</span>
      </div>
      <AttentionAction action={item.action} />
    </div>
  );
};

const ACTION_CLASS =
  'inline-flex items-center gap-2 px-3 py-2 text-[12px] border border-lys-default text-lys-primary hover:bg-lys-surface-interactive active:scale-95 transition-colors cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 shrink-0';

const AttentionAction: React.FC<{ action: AttentionItem['action'] }> = ({ action }) => {
  const openJob = useConsoleStore((s) => s.setActiveModalJobId);
  if (action.type === 'job') {
    return <button type="button" onClick={() => openJob(action.jobId)} className={ACTION_CLASS}>Open job</button>;
  }
  if (action.type === 'route') {
    return <Link to={action.to} className={ACTION_CLASS}>Open floor</Link>;
  }
  return (
    <a href={action.url} target="_blank" rel="noreferrer" className={ACTION_CLASS}>
      Open pull request
      <ExternalLink size={12} aria-hidden="true" />
    </a>
  );
};

const RunningNow: React.FC<{ jobs: Job[]; nowMs: number }> = ({ jobs, nowMs }) => (
  <section aria-label="Running now" className="flex flex-col gap-3">
    <div className="flex items-center justify-between">
      <h2 className="text-[11px] font-medium tracking-wider uppercase text-lys-faint">Running now · {jobs.length}</h2>
      {jobs.length > 0 && <Link to="/floor" className="text-[12px] text-lys-gold hover:underline">Open floor →</Link>}
    </div>
    {jobs.length === 0 ? (
      <EmptyState>No run in progress.</EmptyState>
    ) : (
      <ul className="flex flex-col">
        {jobs.map((job) => (
          <li key={job.id} className="flex items-center gap-4 border-t border-lys-subtle py-2 text-[13px]">
            <span className="flex items-baseline gap-3 min-w-0 flex-1">
              <span title={job.title} className="text-lys-primary truncate min-w-0">{job.title || job.id}</span>
              <span title={job.id} className="font-mono-code text-[11px] text-lys-faint truncate">{job.id}</span>
            </span>
            <span
              className="text-[11px] uppercase tracking-wider font-mono-code shrink-0"
              style={{ color: job.status === 'WAITING_FOR_CAPACITY' ? 'var(--lys-status-warning)' : 'var(--lys-status-success)' }}
            >
              {job.status === 'WAITING_FOR_CAPACITY' ? 'paused' : job.status.toLowerCase()}
            </span>
            <span className="w-16 text-right font-mono-code text-[12px] text-lys-muted shrink-0">
              {formatElapsed(job.startedAt, job.completedAt, nowMs)}
            </span>
          </li>
        ))}
      </ul>
    )}
  </section>
);

const AgentsSummary: React.FC = () => {
  const { agents, loading, error, refetch, updatedAt } = useAgents();
  if (loading && agents.length === 0) return <Card><LoadingState label="Loading agents…" /></Card>;
  if (error && agents.length === 0) return <Card><ErrorState label="Agent registry" error={error} onRetry={refetch} /></Card>;
  return (
    <section aria-label="Agents" className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-[11px] font-medium tracking-wider uppercase text-lys-faint">Agents · {agents.length}</h2>
        <Freshness at={updatedAt} />
      </div>
      <ul className="flex flex-col">
        {agents.map((agent: AgentSummary) => (
          <li key={agent.id} className="flex items-center justify-between gap-3 border-t border-lys-subtle py-2 text-[13px] text-lys-primary">
            <span className="truncate">{agent.displayName}</span>
            <span className="text-[11px] uppercase tracking-wider text-lys-muted">{agent.status}</span>
          </li>
        ))}
      </ul>
    </section>
  );
};
export default OverviewRoute;
