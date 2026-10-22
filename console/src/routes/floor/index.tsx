import React from 'react';
import { useJobs } from '../../api/hooks';
import { ACTIVE_JOB_STATUSES } from '../../api/adapters/httpAdapter';
import { ErrorState, LoadingState, EmptyState, StaleNotice } from '../../components/DataStates';
import { PageHeader, HeaderCount } from '../../components/PageHeader';
import { ActiveJobFloor } from '../../features/floor/ActiveJobFloor';

/** /floor: every active job, with its phases in one column per dependency level. Read-only. */
export const FloorPage: React.FC = () => {
  const { jobs, loading, error, stale, updatedAt, refetch } = useJobs();
  const active = jobs.filter((j) => ACTIVE_JOB_STATUSES.includes(j.status));

  const counts: HeaderCount[] = [{ label: 'ACTIVE', value: active.length, tone: active.length ? 'var(--lys-status-success)' : undefined }];

  return (
    <div className="flex flex-col min-h-full">
      <PageHeader title="Live floor" subtitle="Active jobs · read-only" counts={counts} updatedAt={updatedAt} />

      <div className="flex-1 flex flex-col gap-5 p-6">
        {stale && <StaleNotice label="Jobs" error={error} onRetry={refetch} />}
        {error && jobs.length === 0 && <ErrorState label="Jobs" error={error} onRetry={refetch} />}
        {loading && jobs.length === 0 && <LoadingState label="Loading jobs…" />}
        {!loading && !error && active.length === 0 && <EmptyState>No active jobs</EmptyState>}
        {active.map((job) => (
          <ActiveJobFloor key={job.id} job={job} />
        ))}
      </div>
    </div>
  );
};

export default FloorPage;
