import React from 'react';
import { Job, AgentId } from '../../api/types';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { useAgents } from '../../api/hooks';
import { resolveActorPresentation } from '../../api/actors';

interface QueueTableProps {
  jobs: Job[];
  onSelectJob?: (jobId: string) => void;
  showFilters?: boolean;
}

const PRIO_COLOR: Record<string, string> = {
  P0: 'var(--lys-status-danger)',
  P1: 'var(--lys-status-warning)',
  P2: 'var(--lys-text-muted)',
  P3: 'var(--lys-text-faint)'
};

const STATUS_COLOR: Record<string, string> = {
  QUEUED: 'var(--lys-text-muted)',
  CLAIMED: 'var(--lys-accent-gold)',
  RUNNING: 'var(--lys-status-success)',
  VERIFYING: 'var(--lys-agent-codex)',
  BLOCKED: 'var(--lys-status-warning)',
  FAILED: 'var(--lys-status-danger)',
  COMPLETED: 'var(--lys-text-faint)',
  CANCELLED: 'var(--lys-text-faint)'
};

export const QueueTable: React.FC<QueueTableProps> = ({
  jobs,
  onSelectJob,
  showFilters = true
}) => {
  const { qFilter, setQFilter } = useConsoleStore();
  const { agents } = useAgents();

  const filterOptions = ['All', 'Queued', 'Blocked', 'Completed', 'Cancelled'];

  const filteredJobs = jobs.filter((q) => {
    if (qFilter === 'All') return true;
    return q.status.toUpperCase() === qFilter.toUpperCase();
  });

  return (
    <div className="w-full select-none">
      {/* Filter Tabs */}
      {showFilters && (
        <div className="flex gap-1 px-5 py-3 border-b border-lys-subtle bg-lys-base">
          {filterOptions.map((f) => {
            const isActive = qFilter === f;
            return (
              <button
                key={f}
                onClick={() => setQFilter(f)}
                className={`font-mono-code text-[11px] px-2.5 py-1 border transition-colors cursor-pointer ${
                  isActive
                    ? 'text-lys-primary bg-lys-surface-interactive border-lys-strong'
                    : 'text-lys-muted bg-transparent border-lys-subtle hover:border-lys-strong'
                }`}
              >
                {f}
              </button>
            );
          })}
        </div>
      )}

      {/* Table Header */}
      <div className="flex items-center gap-3.5 px-5 py-2.5 border-b border-lys-subtle font-mono-code text-[11px] tracking-wider text-lys-faint bg-lys-surface-0">
        <span className="w-8 flex-shrink-0">P</span>
        <span className="w-12 flex-shrink-0">JOB</span>
        <span className="flex-1 min-w-[220px]">TASK</span>
        <span className="w-36 flex-shrink-0 hidden md:block">REPOSITORY</span>
        <span className="w-48 flex-shrink-0 hidden lg:block">AGENT CHAIN</span>
        <span className="w-24 flex-shrink-0 text-right">EST TOKENS</span>
        <span className="w-20 flex-shrink-0 text-right hidden sm:block">EST TIME</span>
        <span className="w-24 flex-shrink-0 text-right">STATUS</span>
      </div>

      {/* Table Body */}
      <div className="flex flex-col">
        {filteredJobs.map((q) => {
          const isBlocked = q.status === 'BLOCKED';
          const prioColor = (q.priority && PRIO_COLOR[q.priority]) || 'var(--lys-text-muted)';
          const statusColor = STATUS_COLOR[q.status] || 'var(--lys-text-muted)';

          return (
            <div
              key={q.id}
              onClick={() => onSelectJob?.(q.id)}
              style={{
                backgroundColor: isBlocked ? 'color-mix(in srgb, var(--lys-status-warning) 5%, transparent)' : 'var(--lys-bg-base)'
              }}
              className="flex items-center gap-3.5 px-5 py-3 border-b border-lys-subtle cursor-pointer hover:bg-lys-surface-1 transition-colors"
            >
              {/* Priority */}
              <span
                style={{ color: prioColor }}
                className="w-8 flex-shrink-0 font-mono-code text-[11px] font-semibold"
              >
                {q.priority}
              </span>

              {/* ID */}
              <span className="w-12 flex-shrink-0 font-mono-code text-[12px] text-lys-muted">
                {q.id}
              </span>

              {/* Task Name */}
              <span className="flex-1 min-w-[220px] text-[13px] text-lys-primary truncate">
                {q.title}
              </span>

              {/* Repo */}
              <span className="w-36 flex-shrink-0 hidden md:block font-mono-code text-[11px] text-lys-muted truncate">
                {q.repository}
              </span>

              {/* Agent Chain Badges */}
              <div className="w-48 flex-shrink-0 hidden lg:flex items-center gap-1.5 overflow-hidden">
                {q.assignedAgentIds.map((agId: AgentId, i: number) => {
                  const actor = resolveActorPresentation(agId, agents);
                  const agColor = actor.accentColor || 'var(--lys-text-muted)';
                  return (
                    <React.Fragment key={agId + i}>
                      <div
                        style={{
                          borderColor: agColor,
                          color: agColor,
                          backgroundColor: `color-mix(in srgb, ${agColor} 9%, transparent)`
                        }}
                        className="w-4 h-4 flex items-center justify-center font-mono-code text-[10px] clip-hex"
                        title={actor.displayName}
                      >
                        {actor.displayName ? actor.displayName[0] : agId[0].toUpperCase()}
                      </div>
                      {i < q.assignedAgentIds.length - 1 && (
                        <span className="font-mono-code text-[11px] text-lys-faint">→</span>
                      )}
                    </React.Fragment>
                  );
                })}
              </div>

              {/* Tokens */}
              <span className="w-24 flex-shrink-0 text-right font-mono-code text-[11px] text-lys-muted">
                {q.estimatedTokens || '—'}
              </span>

              {/* Time */}
              <span className="w-20 flex-shrink-0 text-right hidden sm:block font-mono-code text-[11px] text-lys-muted">
                {q.estimatedTime || '—'}
              </span>

              {/* Status */}
              <span
                style={{ color: statusColor }}
                className="w-24 flex-shrink-0 text-right font-mono-code text-[11px] tracking-wider font-semibold"
              >
                {q.status}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
