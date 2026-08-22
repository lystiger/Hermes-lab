import React from 'react';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { useJob, useAgents } from '../../api/hooks';
import { resolveActorPresentation } from '../../api/actors';
import { OperationalThreadView } from '../messaging/OperationalThreadView';

interface JobDetailViewProps {
  jobId?: string;
}

export const JobDetailView: React.FC<JobDetailViewProps> = ({ jobId = '' }) => {
  const { elapsed, allEvents } = useConsoleStore();
  const { job, loading } = useJob(jobId);
  const { agents } = useAgents();

  if (loading && !job) {
    return (
      <div className="w-full p-12 bg-[#0A0B0D] font-mono-code text-[12px] text-[#8C949F] flex items-center justify-center">
        <span>Loading job {jobId}...</span>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="w-full p-12 bg-[#0A0B0D] font-mono-code text-[12px] text-[#8C949F] flex items-center justify-center">
        <span>Job '{jobId}' not found or not loaded.</span>
      </div>
    );
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'RUNNING':
        return '#3FB950';
      case 'COMPLETED':
        return '#5C646E';
      case 'FAILED':
        return '#F2555A';
      case 'CANCELLED':
        return '#5C646E';
      case 'PREPARING':
      case 'QUEUED':
        return '#CBA35C';
      default:
        return '#8C949F';
    }
  };

  const statusCol = getStatusColor(job.status);
  const jobEvents = allEvents.filter((e) => Boolean(e.jobId && (e.jobId === job.id || e.jobId === job.sprintId)));

  return (
    <div className="w-full bg-[#0A0B0D] select-none">
      {/* Header Banner */}
      <div className="p-5 border-b border-[#1F242B] bg-[#0C0E11]">
        <div className="flex items-center gap-3">
          <span className="font-mono-code text-[18px] text-[#5C646E]">{job.id}</span>
          <h2 className="text-[20px] font-semibold text-[#E6E9ED]">
            {job.title}
          </h2>
          <span
            style={{
              color: statusCol,
              borderColor: `${statusCol}55`,
              backgroundColor: `${statusCol}14`
            }}
            className="flex items-center gap-1.5 font-mono-code text-[11px] tracking-wider border px-2 py-0.5"
          >
            {job.status === 'RUNNING' && (
              <span style={{ backgroundColor: statusCol }} className="w-1 h-1 rounded-[1px] animate-pulse" />
            )}
            {job.status}
          </span>
        </div>

        <div className="mt-2.5 flex items-center flex-wrap gap-x-4 gap-y-1 font-mono-code text-[11px] text-[#8C949F]">
          <span>{job.repository}</span>
          {job.branch && <span className="text-[#CBA35C]">{job.branch}</span>}
          <span className="text-[#2A3038]">·</span>
          <span>started {job.startedAt ? job.startedAt.slice(11, 19) : '—'}</span>
          <span>completed {job.completedAt ? job.completedAt.slice(11, 19) : '—'}</span>
          <span>elapsed <span className="text-[#E6E9ED]">{job.status === 'RUNNING' ? elapsed : '—'}</span></span>
          <span>policy <span className="text-[#E6E9ED]">{job.policy || 'governed · serial'}</span></span>
        </div>
      </div>

      {/* Main Body Split */}
      <div className="flex flex-col lg:flex-row items-stretch">
        {/* Left Column: Generic Execution Graph */}
        <div className="w-full lg:w-80 flex-shrink-0 border-r border-b lg:border-b-0 border-[#1F242B] p-5 bg-[#0A0B0D]">
          <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-4">
            EXECUTION GRAPH · {job.phases?.length || job.executionGraph?.length || 0} PHASES
          </div>

          <div style={{ perspective: '800px' }} className="flex flex-col">
            <div style={{ transformStyle: 'preserve-3d' }} className="flex flex-col">
              {(job.phases || []).map((p, idx) => {
                const actor = p.agentId ? resolveActorPresentation(p.agentId, agents) : null;
                const col = actor?.accentColor || '#3A4048';
                const isDone = p.status === 'SUCCEEDED';
                const isActive = p.status === 'RUNNING';
                const isFailed = p.status === 'FAILED';

                return (
                  <div key={p.id || idx}>
                    <div
                      style={{
                        borderColor: isActive ? 'rgba(217,160,91,0.45)' : isDone ? '#1F242B' : isFailed ? 'rgba(242,85,90,0.4)' : '#161A1F',
                        backgroundColor: isActive ? 'rgba(217,160,91,0.06)' : isDone ? '#0E1116' : 'transparent',
                        transform: isActive ? 'translateZ(18px) rotateX(2deg)' : 'translateZ(0)',
                        boxShadow: isActive ? '0 14px 26px -14px rgba(217,160,91,0.55)' : 'none'
                      }}
                      className="flex gap-3 items-start p-3 border"
                    >
                      {/* Mark Icon */}
                      <div
                        style={{
                          borderColor: isDone ? 'rgba(63,185,80,0.6)' : isFailed ? '#F2555A' : isActive ? col : '#2A3038',
                          backgroundColor: isDone ? 'rgba(63,185,80,0.14)' : isFailed ? 'rgba(242,85,90,0.14)' : 'transparent',
                          color: isDone ? '#3FB950' : isFailed ? '#F2555A' : isActive ? col : '#3A4048'
                        }}
                        className="w-4.5 h-4.5 flex-shrink-0 flex items-center justify-center font-mono-code text-[11px] clip-hex"
                      >
                        {isDone ? '✓' : isFailed ? '✕' : isActive ? '●' : '○'}
                      </div>

                      <div className="flex-1 min-w-0">
                        <div
                          style={{ color: isDone || isActive ? '#E6E9ED' : '#5C646E' }}
                          className="font-mono-code text-[11px] tracking-wider font-semibold"
                        >
                          {p.name}
                        </div>
                        <div style={{ color: col }} className="text-[12px] mt-0.5">
                          {p.agentName || actor?.displayName || p.agentId || '—'}
                        </div>
                        <div className="font-mono-code text-[10.5px] text-[#5C646E] mt-0.5">
                          {p.role} {p.commitSha ? `· ${p.commitSha.slice(0, 7)}` : ''}
                        </div>
                      </div>

                      <div className="font-mono-code text-[11px] text-[#5C646E] text-right">
                        {p.durationMs ? `${(p.durationMs / 1000).toFixed(1)}s` : p.status.toLowerCase()}
                      </div>
                    </div>

                    {/* Step Connector */}
                    {idx < (job.phases?.length || 0) - 1 && (
                      <div
                        style={{ backgroundColor: isDone ? 'rgba(63,185,80,0.4)' : '#1F242B' }}
                        className="h-4 w-[1px] ml-5"
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Artifact References */}
          {job.artifacts && job.artifacts.length > 0 && (
            <div className="mt-5 pt-3.5 border-t border-[#1F242B]">
              <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-2.5">
                ARTIFACT REFERENCES
              </div>
              <div className="flex flex-col gap-1.5 font-mono-code text-[11px]">
                {job.artifacts.map((art, idx) => (
                  <div key={art.id || idx} className="flex justify-between text-[#8C949F]">
                    <span className="text-[#CBA35C]">{art.label}</span>
                    <span className="text-[#5C646E] truncate max-w-[120px]" title={art.ref}>{art.ref}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Operational Thread & Execution Events */}
        <div className="flex-1 min-w-0 flex flex-col p-4 gap-5">
          {/* Phase 5 Operational Messaging & Handoffs View */}
          <OperationalThreadView
            jobId={job.id}
            assignedAgentIds={job.assignedAgentIds}
          />

          {/* Execution Trace */}
          <div className="pb-8">
            <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-2.5">
              RUNTIME EVENTS &amp; TRACES · {job.id}
            </div>
            <div className="flex flex-col">
              {jobEvents.length === 0 ? (
                <div className="py-4 font-mono-code text-[11px] text-[#5C646E]">
                  No trace events recorded for this job yet.
                </div>
              ) : (
                jobEvents.slice(0, 15).map((e) => (
                  <div
                    key={e.id}
                    className="flex items-center gap-3.5 py-1 font-mono-code text-[11px] border-b border-[#101216]"
                  >
                    <span className="w-24 text-[#5C646E]">{e.ts}</span>
                    <span
                      style={{ color: e.source.accentColor || '#8C949F' }}
                      className="w-16 font-medium"
                    >
                      {e.source.displayName}
                    </span>
                    <span className="w-28 text-[#8C949F]">{e.kind}</span>
                    <span className="flex-1 min-w-0 text-[#B7BEC7] truncate font-sans">
                      {e.detail}
                    </span>
                    <span className="w-16 text-right text-[#8C949F]">{e.dur}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
