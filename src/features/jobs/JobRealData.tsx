import React from 'react';
import { useJobObservations, useJobRuns, useJobTasks, useJobTelemetry } from '../../api/hooks';
import { describeError } from '../../api/mapping';
import { EmptyState, ErrorState, Freshness, LoadingState, UnknownValue } from '../../components/DataStates';
import { JobDetail } from '../../api/types';
import { explainFailure } from './jobEvents';

const SECTION = 'font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-2.5';

const Section: React.FC<{ title: string; updatedAt?: number | null; children: React.ReactNode }> = ({
  title,
  updatedAt,
  children
}) => (
  <div className="pb-5">
    <div className="flex items-center justify-between mb-2.5">
      <span className={SECTION}>{title}</span>
      {updatedAt !== undefined && <Freshness at={updatedAt} />}
    </div>
    {children}
  </div>
);

/** Failure explanation: what Hermes reported as the reason, shown as an error, not as a neutral note. */
export const JobFailure: React.FC<{ job: JobDetail }> = ({ job }) => {
  const explanation = explainFailure(job);
  if (!explanation) return null;
  return (
    <div role="alert" className="mb-5 p-3 border border-[rgba(242,85,90,0.35)] bg-[rgba(242,85,90,0.05)] font-mono-code text-[11px]">
      <div className="text-[#F2555A] font-semibold">{explanation.headline}</div>
      <ul className="mt-1.5 flex flex-col gap-1 text-[#D7DCE2] break-words">
        {explanation.lines.map((line, i) => (
          <li key={i}>{line}</li>
        ))}
      </ul>
    </div>
  );
};

/** Job token totals from GET /jobs/{id}/telemetry. Zero means no usage was tracked for this job. */
export const JobTokens: React.FC<{ jobId: string }> = ({ jobId }) => {
  const { telemetry, loading, error, refetch } = useJobTelemetry(jobId);
  if (loading && !telemetry) return <span className="text-[#5C646E]">tokens loading…</span>;
  if (error && !telemetry) {
    return (
      <span className="text-[#F2555A]" title={error.message}>
        tokens unavailable{' '}
        <button type="button" onClick={refetch} className="underline cursor-pointer">retry</button>
      </span>
    );
  }
  if (!telemetry) return <UnknownValue reason="Token telemetry not loaded" />;
  if (telemetry.totalTokens === 0) {
    return (
      <span title="No token usage has been tracked for this job. That is not proof that none was spent.">
        0 tracked <span className="text-[#5C646E]">(no usage recorded)</span>
      </span>
    );
  }
  return (
    <span title={`input ${telemetry.inputTokens} · output ${telemetry.outputTokens} · cached ${telemetry.cachedTokens}`}>
      {telemetry.totalTokens} <span className="text-[#5C646E]">tokens tracked for this job</span>
    </span>
  );
};

export const JobTasks: React.FC<{ jobId: string }> = ({ jobId }) => {
  const { tasks, loading, error, updatedAt, refetch } = useJobTasks(jobId);
  return (
    <Section title={`TASKS · ${tasks.length}`} updatedAt={updatedAt}>
      {loading && tasks.length === 0 && <LoadingState label="Loading tasks…" />}
      {error && <ErrorState label="Tasks" error={error} onRetry={refetch} />}
      {!loading && !error && tasks.length === 0 && <EmptyState>Hermes recorded no tasks for this job.</EmptyState>}
      <div className="flex flex-col gap-1.5 font-mono-code text-[11px]">
        {tasks.map((t) => (
          <div key={t.taskId} className="p-2 bg-[#101216] border border-[#1F242B]">
            <div className="flex justify-between gap-3">
              <span className="text-[#E6E9ED] font-sans text-[12px]">{t.description || t.taskId}</span>
              <span className="text-[#8C949F]">{t.status}</span>
            </div>
            <div className="mt-1 text-[#5C646E]">
              {t.taskId} · attempt {t.attempt}
              {t.maxAttempts !== null ? ` of ${t.maxAttempts}` : ''}
              {t.assignedActor ? ` · ${t.assignedActor}` : ''}
              {t.dependencies.length > 0 ? ` · after ${t.dependencies.join(', ')}` : ''}
            </div>
            {t.error !== null && t.error !== undefined && (
              <div className="mt-1 text-[#F2555A] break-words">{describeError(t.error)}</div>
            )}
          </div>
        ))}
      </div>
    </Section>
  );
};

export const JobRuns: React.FC<{ jobId: string }> = ({ jobId }) => {
  const { runs, loading, error, updatedAt, refetch } = useJobRuns(jobId);
  return (
    <Section title={`RUNS · ${runs.length}`} updatedAt={updatedAt}>
      {loading && runs.length === 0 && <LoadingState label="Loading runs…" />}
      {error && <ErrorState label="Runs" error={error} onRetry={refetch} />}
      {!loading && !error && runs.length === 0 && <EmptyState>Hermes recorded no runs for this job.</EmptyState>}
      <div className="flex flex-col gap-1.5 font-mono-code text-[11px]">
        {runs.map((r) => (
          <div key={r.runId} className="p-2 bg-[#101216] border border-[#1F242B] flex flex-wrap justify-between gap-2">
            <span className="text-[#D7DCE2]">{r.runId}</span>
            <span className="text-[#8C949F]">{r.actorId} · {r.taskId} · attempt {r.attempt}</span>
            <span className="text-[#E6E9ED]">{r.status}</span>
            {r.exitReason && <span className="w-full text-[#5C646E]">exit: {r.exitReason}</span>}
            {r.error !== null && r.error !== undefined && (
              <span className="w-full text-[#F2555A] break-words">{describeError(r.error)}</span>
            )}
          </div>
        ))}
      </div>
    </Section>
  );
};

export const JobObservations: React.FC<{ jobId: string }> = ({ jobId }) => {
  const { observations, loading, error, updatedAt, refetch } = useJobObservations(jobId);
  return (
    <Section title={`OBSERVATIONS · ${observations.length}`} updatedAt={updatedAt}>
      {loading && observations.length === 0 && <LoadingState label="Loading observations…" />}
      {error && <ErrorState label="Observations" error={error} onRetry={refetch} />}
      {!loading && !error && observations.length === 0 && (
        <EmptyState>Hermes recorded no observations for this job.</EmptyState>
      )}
      <div className="flex flex-col gap-1.5 font-mono-code text-[11px]">
        {observations.map((o) => (
          <div key={o.observationId} className="p-2 bg-[#101216] border border-[#1F242B]">
            <div className="text-[#8C949F]">
              {o.kind}
              {o.actorId ? ` · ${o.actorId}` : ''}
              {o.confidence !== null ? ` · confidence ${o.confidence}` : ''}
            </div>
            <div className="mt-1 text-[#D7DCE2] font-sans text-[12px] break-words">{o.content}</div>
          </div>
        ))}
      </div>
    </Section>
  );
};
