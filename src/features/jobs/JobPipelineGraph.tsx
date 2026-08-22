import React from 'react';
import { PipelineStep } from '../../api/types';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { resolveActorRef } from '../../api/mock/actors';

interface JobPipelineGraphProps {
  steps?: PipelineStep[];
}

export const JobPipelineGraph: React.FC<JobPipelineGraphProps> = ({ steps }) => {
  const { hardenTokens, liveMotion } = useConsoleStore();

  const defaultPhases: PipelineStep[] = [
    { id: '1', phase: 'BUILD', agentId: 'gemini', agentName: 'Gemini', note: 'closed 30.4k', state: 'COMPLETE', task: 'Build', meta: '' },
    { id: '2', phase: 'HARDEN', agentId: 'claude', agentName: 'Claude', note: `02:14 · ${hardenTokens}`, state: 'RUNNING', task: 'Harden', meta: '' },
    { id: '3', phase: 'VERIFY', agentId: 'codex', agentName: 'Codex', note: 'staged ~19k', state: 'QUEUED', task: 'Verify', meta: '' },
    { id: '4', phase: 'COMPLETE', agentId: 'elysia', agentName: 'Elysia', note: 'auto-merge & notify', state: 'idle', task: 'Complete', meta: '' }
  ];

  const graphSteps = steps || defaultPhases;

  return (
    <div style={{ perspective: '900px' }} className="w-full select-none">
      <div
        style={{
          transform: 'rotateX(9deg)',
          transformStyle: 'preserve-3d'
        }}
        className="flex items-start relative"
      >
        {graphSteps.map((p, idx) => {
          const actor = p.agentId ? resolveActorRef(p.agentId) : null;
          const col = actor?.accentColor || '#3A4048';
          const isDone = p.state === 'COMPLETE';
          const isActive = p.state === 'RUNNING';

          return (
            <div
              key={p.id || idx}
              className="flex-1 relative flex flex-col items-start"
            >
              {/* Connecting Line */}
              {idx < graphSteps.length - 1 && (
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
                    borderColor: isDone ? 'rgba(63,185,80,0.6)' : isActive ? col : '#2A3038',
                    backgroundColor: isDone ? 'rgba(63,185,80,0.12)' : isActive ? 'rgba(217,160,91,0.16)' : '#0E1116',
                    boxShadow: isActive ? '0 6px 14px -6px rgba(217,160,91,0.5)' : 'none',
                    transform: 'rotate(45deg) translateZ(6px)'
                  }}
                  className="absolute w-[22px] h-[22px] border"
                />
                <div
                  style={{
                    backgroundColor: isDone ? '#3FB950' : isActive ? col : '#2A3038',
                    transform: 'rotate(45deg) translateZ(12px)'
                  }}
                  className={`absolute w-2 h-2 ${isActive && liveMotion ? 'animate-pulse' : ''}`}
                />
              </div>

              {/* Phase Info */}
              <div
                style={{ color: isDone || isActive ? '#E6E9ED' : '#5C646E' }}
                className="mt-3 font-mono-code text-[12px] tracking-wider font-semibold"
              >
                {p.phase}
              </div>

              <div
                style={{ color: p.state === 'idle' ? '#3A4048' : col }}
                className="mt-1 text-[11px]"
              >
                {p.agentName || actor?.displayName || '—'}
              </div>

              <div className="mt-0.5 font-mono-code text-[11px] text-[#5C646E]">
                {p.note}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
