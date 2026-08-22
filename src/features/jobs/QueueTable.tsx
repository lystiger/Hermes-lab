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
  P0: '#F2555A',
  P1: '#E3A008',
  P2: '#8C949F',
  P3: '#5C646E'
};

const STATUS_COLOR: Record<string, string> = {
  QUEUED: '#8C949F',
  CLAIMED: '#CBA35C',
  RUNNING: '#3FB950',
  VERIFYING: '#4EC9A0',
  BLOCKED: '#E3A008',
  FAILED: '#F2555A',
  COMPLETED: '#5C646E',
  CANCELLED: '#5C646E'
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
        <div className="flex gap-1 px-5 py-3 border-b border-[#1F242B] bg-[#0A0B0D]">
          {filterOptions.map((f) => {
            const isActive = qFilter === f;
            return (
              <button
                key={f}
                onClick={() => setQFilter(f)}
                className={`font-mono-code text-[11px] px-2.5 py-1 border transition-colors cursor-pointer ${
                  isActive
                    ? 'text-[#E6E9ED] bg-[#1F242B] border-[#3A4048]'
                    : 'text-[#8C949F] bg-transparent border-[#1F242B] hover:border-[#3A4048]'
                }`}
              >
                {f}
              </button>
            );
          })}
        </div>
      )}

      {/* Table Header */}
      <div className="flex items-center gap-3.5 px-5 py-2.5 border-b border-[#1F242B] font-mono-code text-[11px] tracking-wider text-[#5C646E] bg-[#0C0E11]">
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
          const prioColor = PRIO_COLOR[q.priority || 'P1'] || '#8C949F';
          const statusColor = STATUS_COLOR[q.status] || '#8C949F';

          return (
            <div
              key={q.id}
              onClick={() => onSelectJob?.(q.id)}
              style={{
                backgroundColor: isBlocked ? 'rgba(227,160,8,0.05)' : '#0A0B0D'
              }}
              className="flex items-center gap-3.5 px-5 py-3 border-b border-[#14171C] cursor-pointer hover:bg-[#12151A] transition-colors"
            >
              {/* Priority */}
              <span
                style={{ color: prioColor }}
                className="w-8 flex-shrink-0 font-mono-code text-[11px] font-semibold"
              >
                {q.priority}
              </span>

              {/* ID */}
              <span className="w-12 flex-shrink-0 font-mono-code text-[12px] text-[#8C949F]">
                {q.id}
              </span>

              {/* Task Name */}
              <span className="flex-1 min-w-[220px] text-[13px] text-[#E6E9ED] truncate">
                {q.title}
              </span>

              {/* Repo */}
              <span className="w-36 flex-shrink-0 hidden md:block font-mono-code text-[11px] text-[#8C949F] truncate">
                {q.repository}
              </span>

              {/* Agent Chain Badges */}
              <div className="w-48 flex-shrink-0 hidden lg:flex items-center gap-1.5 overflow-hidden">
                {q.assignedAgentIds.map((agId: AgentId, i: number) => {
                  const actor = resolveActorPresentation(agId, agents);
                  const agColor = actor.accentColor || '#8C949F';
                  return (
                    <React.Fragment key={agId + i}>
                      <div
                        style={{
                          borderColor: agColor,
                          color: agColor,
                          backgroundColor: `${agColor}18`
                        }}
                        className="w-4 h-4 flex items-center justify-center font-mono-code text-[10px] clip-hex"
                        title={actor.displayName}
                      >
                        {actor.displayName ? actor.displayName[0] : agId[0].toUpperCase()}
                      </div>
                      {i < q.assignedAgentIds.length - 1 && (
                        <span className="font-mono-code text-[11px] text-[#3A4048]">→</span>
                      )}
                    </React.Fragment>
                  );
                })}
              </div>

              {/* Tokens */}
              <span className="w-24 flex-shrink-0 text-right font-mono-code text-[11px] text-[#8C949F]">
                {q.estimatedTokens || '—'}
              </span>

              {/* Time */}
              <span className="w-20 flex-shrink-0 text-right hidden sm:block font-mono-code text-[11px] text-[#8C949F]">
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
