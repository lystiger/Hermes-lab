import React from 'react';
import { Job } from '../../api/types';
import { useAgents, useJob } from '../../api/hooks';
import { resolveActorPresentation } from '../../api/actors';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { useNow } from '../execution/useNow';
import { timelineRows } from '../jobs/runTimeline';
import { Card } from '../../components/Card';
import { CopyId } from '../../components/CopyId';
import { EmptyState, ErrorState, LoadingState, UNKNOWN } from '../../components/DataStates';
import { FloorCard } from './FloorCard';
import { FloorPhase, floorCardState, floorLevels, latestPhaseEvent } from './floorLayout';

/**
 * One active job on the live floor: its phases in one column per dependency level. The job's detail is loaded
 * here, so each job keeps its own refresh and clock.
 */
export const ActiveJobFloor: React.FC<{ job: Job }> = ({ job }) => {
  const { job: detail, error, refetch } = useJob(job.id);
  const { agents } = useAgents();
  const { allEvents } = useConsoleStore();
  const nowMs = useNow(1000);

  if (!detail) {
    return (
      <Card label={job.title}>
        {error ? <ErrorState label={`Job ${job.id}`} error={error} onRetry={refetch} /> : <LoadingState label={`Loading ${job.title}…`} />}
      </Card>
    );
  }

  // Phases are shown in spec order. Dependencies are read from the raw phase where Hermes sends them.
  const phaseById = new Map((detail.phases ?? []).map((p) => [p.id || `phase-${p.order}`, p]));
  const phases: FloorPhase[] = timelineRows(detail).map((row) => ({
    ...row,
    dependencies: phaseById.get(row.key)?.dependencies
  }));
  const levels = floorLevels(phases);

  const jobIds = [job.id, job.sprintId].filter((id): id is string => !!id);

  return (
    <Card label={`Job ${detail.title}`}>
      <div className="p-4 flex flex-col gap-4">
        <header className="flex flex-wrap items-center gap-3 min-w-0">
          <CopyId truncate value={detail.id} className="max-w-[40%] text-lys-faint" />
          <h2 title={detail.title} className="min-w-0 truncate text-[15px] font-semibold text-lys-primary">{detail.title}</h2>
          <span className="ml-auto text-[10px] tracking-wider uppercase text-lys-secondary">{detail.status}</span>
        </header>

        {phases.length === 0 ? (
          <EmptyState>Hermes reported no phases for this job</EmptyState>
        ) : (
          <div className="flex gap-4 overflow-x-auto pb-1">
            {levels.map((column, idx) => (
              <section key={idx} aria-label={`Level ${idx + 1}`} className="flex flex-col gap-2 w-[240px] shrink-0">
                <div className="text-[11px] font-medium tracking-wider uppercase text-lys-faint">
                  Level {idx + 1} · {column.length}
                </div>
                {column.map((phase) => {
                  const latestEvent = latestPhaseEvent(phase, jobIds, allEvents);
                  const card = floorCardState(phase, latestEvent, nowMs);
                  const agent = phase.agentId ? resolveActorPresentation(phase.agentId, agents) : null;
                  const phaseDetail = phaseById.get(phase.key)?.detail;
                  const liveLine = latestEvent?.detail || latestEvent?.kind || phaseDetail || UNKNOWN;
                  return (
                    <FloorCard key={phase.key} phase={phase} card={card} agent={agent} latestEvent={latestEvent} liveLine={liveLine} />
                  );
                })}
              </section>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
};
