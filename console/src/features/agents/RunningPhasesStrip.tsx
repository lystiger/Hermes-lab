import React from 'react';
import { Job } from '../../api/types';
import { useAgents, useJob, useJobs } from '../../api/hooks';
import { ACTIVE_JOB_STATUSES } from '../../api/adapters/httpAdapter';
import { resolveActorPresentation } from '../../api/actors';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { useNow } from '../execution/useNow';
import { formatDuration, phaseLabel, timelineRows } from '../jobs/runTimeline';

/**
 * Who is running what right now, across every active job: one chip per running phase, labelled with
 * the phase's role. Roles belong to phases, not agents, so one agent can appear under several roles.
 * Renders nothing while no job is active.
 */
export const RunningPhasesStrip: React.FC = () => {
  const { jobs } = useJobs();
  const activeJobs = jobs.filter((j) => ACTIVE_JOB_STATUSES.includes(j.status));
  if (activeJobs.length === 0) return null;

  return (
    <section aria-label="Running now" className="px-4 py-3 border-b border-lys-subtle bg-lys-base">
      <div className="text-[11px] font-medium tracking-wider uppercase text-lys-faint mb-2">Running now · by role</div>
      <ul className="flex flex-wrap gap-2">
        {activeJobs.map((job) => <JobRunningPhases key={job.id} job={job} />)}
      </ul>
    </section>
  );
};

const JobRunningPhases: React.FC<{ job: Job }> = ({ job }) => {
  const { job: detail } = useJob(job.id);
  const { agents } = useAgents();
  const { setActiveModalJobId } = useConsoleStore();
  const nowMs = useNow(1000);
  if (!detail) return null;

  const running = timelineRows(detail).filter((r) => r.state === 'RUNNING' || r.state === 'CLAIMED');
  return (
    <>
      {running.map((r) => {
        const actor = r.agentId ? resolveActorPresentation(r.agentId, agents) : null;
        return (
          <li key={`${job.id}:${r.key}`}>
            <button
              type="button"
              onClick={() => setActiveModalJobId(job.id)}
              title={`${job.title} · ${r.name}`}
              className="flex items-center gap-2 px-2.5 py-1.5 border border-lys-subtle bg-lys-surface-2 hover:bg-lys-surface-interactive text-[12px] whitespace-nowrap cursor-pointer max-w-[26rem]"
            >
              <span className="text-[10px] tracking-wider uppercase text-lys-faint">{r.role ?? 'phase'}</span>
              <span style={{ color: actor?.accentColor }} className="font-medium">{actor?.displayName || r.agentId || '—'}</span>
              <span className="text-lys-primary">{phaseLabel(r.name)}</span>
              <span className="text-lys-faint min-w-0 truncate">{job.title}</span>
              {r.startMs !== null && <span className="font-mono-code text-[11px] text-lys-muted">{formatDuration(nowMs - r.startMs)}</span>}
            </button>
          </li>
        );
      })}
    </>
  );
};
