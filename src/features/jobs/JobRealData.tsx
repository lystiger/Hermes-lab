import React from 'react';
import { useJobObservations, useJobRuns, useJobTasks, useJobTelemetry } from '../../api/hooks';
import { describeError } from '../../api/mapping';
import { EmptyState, Freshness, LoadingState, ResourceError, UnknownValue } from '../../components/DataStates';
import { JobDetail } from '../../api/types';
import { describeRecord, explainFailure, verificationResultLines } from './jobEvents';
import { formatTimeOfDay } from '../time/format';

const SECTION = 'font-sans text-[11px] tracking-wider text-lys-faint mb-2.5';

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
    <div role="alert" className="mb-5 p-3 border border-lys-danger/35 bg-lys-danger/5 font-sans text-[11px]">
      <div className="text-lys-danger font-semibold">{explanation.headline}</div>
      <ul className="mt-1.5 flex flex-col gap-1 text-lys-primary break-words">
        {explanation.lines.map((line, i) => (
          <li key={i} className="line-clamp-2" title={line}>{line}</li>
        ))}
      </ul>
    </div>
  );
};

/** Job token totals from GET /jobs/{id}/telemetry. Zero means no usage was tracked for this job. */
export const JobTokens: React.FC<{ jobId: string }> = ({ jobId }) => {
  const { telemetry, loading, error, stale, updatedAt, refetch } = useJobTelemetry(jobId);
  if (loading && !telemetry) return <span className="text-lys-faint">tokens loading…</span>;
  if (error && !telemetry) {
    return (
      <span className="text-lys-danger" title={error.message}>
        tokens unavailable{' '}
        <button type="button" onClick={refetch} className="underline cursor-pointer">retry</button>
      </span>
    );
  }
  if (!telemetry) return <UnknownValue reason="Token telemetry not loaded" />;
  // A failed refresh keeps the last good total, marked stale, with the error and a retry (M5 F2).
  if (stale) {
    return (
      <span className="inline-flex flex-wrap items-center gap-2">
        <span>{telemetry.totalTokens} <span className="text-lys-faint">tokens (last loaded {updatedAt ? formatTimeOfDay(updatedAt) : '—'})</span></span>
        <span role="alert" className="text-lys-warning" title={error?.message}>
          stale: refresh failed{' '}
          <button type="button" onClick={refetch} className="underline cursor-pointer">retry</button>
        </span>
      </span>
    );
  }
  if (telemetry.totalTokens === 0) {
    return (
      <span title="No token usage has been tracked for this job. That is not proof that none was spent.">
        0 tracked <span className="text-lys-faint">(no usage recorded)</span>
      </span>
    );
  }
  return (
    <span title={`input ${telemetry.inputTokens} · output ${telemetry.outputTokens} · cached ${telemetry.cachedTokens}`}>
      {telemetry.totalTokens} <span className="text-lys-faint">tokens tracked for this job</span>
    </span>
  );
};

export const JobTasks: React.FC<{ jobId: string }> = ({ jobId }) => {
  const { tasks, loading, error, stale, updatedAt, refetch } = useJobTasks(jobId);
  return (
    <Section title={`TASKS · ${tasks.length}`} updatedAt={updatedAt}>
      {loading && tasks.length === 0 && <LoadingState label="Loading tasks…" />}
      <ResourceError label="Tasks" error={error} hasData={stale || tasks.length > 0} updatedAt={updatedAt} onRetry={refetch} />
      {!loading && !error && tasks.length === 0 && <EmptyState>No tasks recorded</EmptyState>}
      <div className="flex flex-col gap-1.5 font-sans text-[11px]">
        {tasks.map((t) => (
          <div key={t.taskId} className="p-2 bg-lys-surface-1 border border-lys-subtle">
            <div className="flex justify-between gap-3">
              <span className="text-lys-primary font-sans text-[12px]">{t.description || t.taskId}</span>
              <span className="text-lys-muted">{t.status}</span>
            </div>
            <div className="mt-1 text-lys-faint">
              {t.taskId} · attempt {t.attempt}
              {t.maxAttempts !== null ? ` of ${t.maxAttempts}` : ''}
              {t.assignedActor ? ` · ${t.assignedActor}` : ''}
              {t.dependencies.length > 0 ? ` · after ${t.dependencies.join(', ')}` : ''}
            </div>
            {t.error !== null && t.error !== undefined && (
              <div className="mt-1 text-lys-danger break-words line-clamp-2" title={describeError(t.error)}>{describeError(t.error)}</div>
            )}
          </div>
        ))}
      </div>
    </Section>
  );
};

export const JobRuns: React.FC<{ jobId: string }> = ({ jobId }) => {
  const { runs, loading, error, stale, updatedAt, refetch } = useJobRuns(jobId);
  return (
    <Section title={`RUNS · ${runs.length}`} updatedAt={updatedAt}>
      {loading && runs.length === 0 && <LoadingState label="Loading runs…" />}
      <ResourceError label="Runs" error={error} hasData={stale || runs.length > 0} updatedAt={updatedAt} onRetry={refetch} />
      {!loading && !error && runs.length === 0 && <EmptyState>No runs recorded</EmptyState>}
      <div className="flex flex-col gap-1.5 font-sans text-[11px]">
        {runs.map((r) => (
          <div key={r.runId} className="p-2 bg-lys-surface-1 border border-lys-subtle flex flex-wrap justify-between gap-2">
            <span className="text-lys-primary">{r.runId}</span>
            <span className="text-lys-muted">{r.actorId} · {r.taskId} · attempt {r.attempt}</span>
            <span className="text-lys-primary">{r.status}</span>
            {r.exitReason && <span className="w-full text-lys-faint">exit: {r.exitReason}</span>}
            {r.error !== null && r.error !== undefined && (
              <span className="w-full text-lys-danger break-words line-clamp-2" title={describeError(r.error)}>{describeError(r.error)}</span>
            )}
          </div>
        ))}
      </div>
    </Section>
  );
};

export const JobObservations: React.FC<{ jobId: string }> = ({ jobId }) => {
  const { observations, loading, error, stale, updatedAt, refetch } = useJobObservations(jobId);
  return (
    <Section title={`OBSERVATIONS · ${observations.length}`} updatedAt={updatedAt}>
      {loading && observations.length === 0 && <LoadingState label="Loading observations…" />}
      <ResourceError label="Observations" error={error} hasData={stale || observations.length > 0} updatedAt={updatedAt} onRetry={refetch} />
      {!loading && !error && observations.length === 0 && (
        <EmptyState>No observations recorded</EmptyState>
      )}
      <div className="flex flex-col gap-1.5 font-sans text-[11px]">
        {observations.map((o) => (
          <div key={o.observationId} className="p-2 bg-lys-surface-1 border border-lys-subtle">
            <div className="text-lys-muted">
              {o.kind}
              {o.actorId ? ` · ${o.actorId}` : ''}
              {o.confidence !== null ? ` · confidence ${o.confidence}` : ''}
            </div>
            <div className="mt-1 text-lys-primary font-sans text-[12px] break-words">{o.content}</div>
          </div>
        ))}
      </div>
    </Section>
  );
};

/**
 * Verification, attempts and repair/replan counts exactly as Hermes reports them. An absent value is shown as
 * not reported; no totals, retry limits or pass counts are derived.
 */
export const JobDiagnostics: React.FC<{ job: JobDetail }> = ({ job }) => {
  const v = job.verification as { status?: unknown; results?: unknown } | null | undefined;
  const history = job.retryHistory;
  return (
    <Section title="DIAGNOSTICS">
      <div className="flex flex-col gap-3 font-sans text-[11px]">
        <div className="p-2 bg-lys-surface-1 border border-lys-subtle">
          <div className="text-lys-muted tracking-wider mb-1">VERIFICATION</div>
          {v === null || v === undefined ? (
            <EmptyState>No verification recorded</EmptyState>
          ) : (
            <div className="flex flex-col gap-1 text-lys-secondary">
              <span>status: {typeof v.status === 'string' ? v.status : <UnknownValue reason="verification has no status" />}</span>
              {verificationResultLines(v.results).length === 0 ? (
                <span className="text-lys-faint">no result details were reported</span>
              ) : (
                verificationResultLines(v.results).map((line, i) => (
                  <span key={i} className="break-words">{line}</span>
                ))
              )}
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="p-2 bg-lys-surface-1 border border-lys-subtle">
            <div className="text-lys-muted tracking-wider">REPAIRS</div>
            <div className="text-lys-primary text-[14px]">
              {job.repairCount ?? <UnknownValue reason="Hermes did not report a repair count" />}
            </div>
          </div>
          <div className="p-2 bg-lys-surface-1 border border-lys-subtle">
            <div className="text-lys-muted tracking-wider">REPLANS</div>
            <div className="text-lys-primary text-[14px]">
              {job.replanCount ?? <UnknownValue reason="Hermes did not report a replan count" />}
            </div>
          </div>
        </div>

        <div className="p-2 bg-lys-surface-1 border border-lys-subtle">
          <div className="text-lys-muted tracking-wider mb-1">RETRY HISTORY</div>
          {history === undefined ? (
            <span className="text-lys-faint">not reported by Hermes for this job</span>
          ) : history.length === 0 ? (
            <span className="text-lys-faint">no retries recorded</span>
          ) : (
            <ul className="flex flex-col gap-1 text-lys-secondary">
              {history.map((h, i) => (
                <li key={i} className="break-words">{describeRecord(h)}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Section>
  );
};
