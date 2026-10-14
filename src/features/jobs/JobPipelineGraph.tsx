import React from 'react';
import { PipelineStep, PipelineStepState } from '../../api/types';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { useAgents } from '../../api/hooks';
import { resolveActorPresentation } from '../../api/actors';
import { EmptyState } from '../../components/DataStates';

interface JobPipelineGraphProps {
  steps: PipelineStep[];
}

const STATE_LABEL: Record<PipelineStepState, string> = {
  COMPLETED: 'completed',
  RUNNING: 'running',
  QUEUED: 'queued',
  CLAIMED: 'claimed',
  BLOCKED: 'blocked',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
  SKIPPED: 'skipped',
  UNKNOWN: 'unknown status',
  IDLE: 'idle'
};

/** Renders only the steps it is given. No phases are invented when there are none. */
export const JobPipelineGraph: React.FC<JobPipelineGraphProps> = ({ steps }) => {
  const { liveMotion } = useConsoleStore();
  const { agents } = useAgents();

  if (steps.length === 0) {
    return <EmptyState>No phases reported for this job yet.</EmptyState>;
  }

  return (
    <div style={{ perspective: '900px' }} className="w-full select-none">
      <div
        style={{
          transform: 'rotateX(9deg)',
          transformStyle: 'preserve-3d'
        }}
        className="flex items-start relative"
      >
        {steps.map((p, idx) => {
          const actor = p.agentId ? resolveActorPresentation(p.agentId, agents) : null;
          const col = actor?.accentColor || '#3A4048';
          const isDone = p.state === 'COMPLETED';
          const isActive = p.state === 'RUNNING';
          const isFailed = p.state === 'FAILED';

          return (
            <div
              key={p.id || idx}
              className="flex-1 relative flex flex-col items-start"
            >
              {/* Connecting Line */}
              {idx < steps.length - 1 && (
                <div
                  style={{
                    backgroundColor: isDone ? 'rgba(63,185,80,0.5)' : '#1F242B'
                  }}
                  className="absolute left-6 right-0 top-[11px] h-[1px]"
                />
              )}

              {/* Diamond Node */}
              <div className="relative w-6 h-6 flex items-center justify-center bg-[#0A0B0D] z-10">
                <div
                  style={{
                    borderColor: isDone ? 'rgba(63,185,80,0.6)' : isFailed ? 'rgba(242,85,90,0.6)' : isActive ? col : '#2A3038',
                    backgroundColor: isDone ? 'rgba(63,185,80,0.12)' : isFailed ? 'rgba(242,85,90,0.12)' : isActive ? 'rgba(217,160,91,0.16)' : '#0E1116',
                    boxShadow: isActive ? '0 6px 14px -6px rgba(217,160,91,0.5)' : 'none',
                    transform: 'rotate(45deg) translateZ(6px)'
                  }}
                  className="absolute w-[22px] h-[22px] border"
                />
                <div
                  style={{
                    backgroundColor: isDone ? '#3FB950' : isFailed ? '#F2555A' : isActive ? col : '#2A3038',
                    transform: 'rotate(45deg) translateZ(12px)'
                  }}
                  className={`absolute w-2 h-2 ${isActive && liveMotion ? 'animate-pulse' : ''}`}
                />
              </div>

              {/* Phase Info */}
              <div
                style={{ color: isDone || isActive || isFailed ? '#E6E9ED' : '#5C646E' }}
                className="mt-3 font-mono-code text-[12px] tracking-wider font-semibold"
              >
                {p.phase}
              </div>

              <div
                style={{ color: p.state === 'IDLE' ? '#3A4048' : col }}
                className="mt-1 text-[11px]"
              >
                {p.agentName || actor?.displayName || '—'}
              </div>

              <div className="mt-0.5 font-mono-code text-[11px] text-[#5C646E]">
                {STATE_LABEL[p.state]}{p.meta ? ` · ${p.meta}` : ''}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
