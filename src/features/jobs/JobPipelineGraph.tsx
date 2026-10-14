import React from 'react';
import { PipelineStep, PipelineStepState } from '../../api/types';
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
          const col = actor?.accentColor || 'var(--lys-border-strong)';
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
                    backgroundColor: isDone ? 'color-mix(in srgb, var(--lys-status-success) 50%, transparent)' : 'var(--lys-border-subtle)'
                  }}
                  className="absolute left-6 right-0 top-[11px] h-[1px]"
                />
              )}

              {/* Diamond Node */}
              <div className="relative w-6 h-6 flex items-center justify-center bg-lys-base z-10">
                <div
                  style={{
                    borderColor: isDone ? 'color-mix(in srgb, var(--lys-status-success) 60%, transparent)' : isFailed ? 'color-mix(in srgb, var(--lys-status-danger) 60%, transparent)' : isActive ? col : 'var(--lys-border-default)',
                    backgroundColor: isDone ? 'color-mix(in srgb, var(--lys-status-success) 12%, transparent)' : isFailed ? 'color-mix(in srgb, var(--lys-status-danger) 12%, transparent)' : isActive ? 'color-mix(in srgb, var(--lys-agent-claude) 16%, transparent)' : 'var(--lys-surface-0)',
                    boxShadow: isActive ? '0 6px 14px -6px color-mix(in srgb, var(--lys-agent-claude) 50%, transparent)' : 'none',
                    transform: 'rotate(45deg) translateZ(6px)'
                  }}
                  className="absolute w-[22px] h-[22px] border"
                />
                <div
                  style={{
                    backgroundColor: isDone ? 'var(--lys-status-success)' : isFailed ? 'var(--lys-status-danger)' : isActive ? col : 'var(--lys-border-default)',
                    transform: 'rotate(45deg) translateZ(12px)'
                  }}
                  className={`absolute w-2 h-2`}
                />
              </div>

              {/* Phase Info */}
              <div
                style={{ color: isDone || isActive || isFailed ? 'var(--lys-text-primary)' : 'var(--lys-text-faint)' }}
                className="mt-3 font-mono-code text-[12px] tracking-wider font-semibold"
              >
                {p.phase}
              </div>

              <div
                style={{ color: p.state === 'IDLE' ? 'var(--lys-text-faint)' : col }}
                className="mt-1 text-[11px]"
              >
                {p.agentName || actor?.displayName || '—'}
              </div>

              <div className="mt-0.5 font-mono-code text-[11px] text-lys-faint">
                {STATE_LABEL[p.state]}{p.meta ? ` · ${p.meta}` : ''}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
