import React from 'react';
import { QueueTable } from '../features/jobs/QueueTable';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useJobs, usePipeline } from '../api/hooks';
import { resolveActorRef } from '../api/mock/actors';

export const QueueRoute: React.FC = () => {
  const { setActiveModalJobId, liveMotion } = useConsoleStore();
  const { jobs } = useJobs();
  const { pipeline } = usePipeline();

  const getStateColor = (state: string) => {
    switch (state) {
      case 'COMPLETE': return '#5C646E';
      case 'RUNNING': return '#3FB950';
      case 'QUEUED': return '#8C949F';
      case 'CLAIMED': return '#CBA35C';
      case 'BLOCKED': return '#E3A008';
      default: return '#5C646E';
    }
  };

  return (
    <div className="flex flex-col pb-10 select-none bg-[#0A0B0D]">
      {/* Execution Order Pipeline Section */}
      <div className="p-5 border-b border-[#1F242B] bg-[#0C0E11]">
        <div className="flex items-center gap-3.5 mb-3 font-mono-code text-[11px]">
          <span className="tracking-wider text-[#5C646E]">EXECUTION ORDER</span>
          <span className="text-[#8C949F]">serial per repository · next handoff ~4 min</span>
        </div>

        <div className="flex flex-col max-w-5xl">
          {pipeline.map((p, idx) => {
            const isRunning = p.state === 'RUNNING';
            const isBlocked = p.state === 'BLOCKED';
            const actor = p.agentId ? resolveActorRef(p.agentId) : null;
            const agentCol = actor?.accentColor || '#8C949F';
            const stateCol = getStateColor(p.state);
            const agentName = p.agentName || actor?.displayName || '—';

            return (
              <div key={p.id || idx}>
                <div
                  onClick={() => setActiveModalJobId(p.id)}
                  style={{
                    borderColor: isRunning ? 'rgba(217,160,91,0.45)' : isBlocked ? 'rgba(227,160,8,0.3)' : '#1F242B',
                    backgroundColor: isRunning ? 'rgba(217,160,91,0.06)' : isBlocked ? 'rgba(227,160,8,0.04)' : '#0C0E11'
                  }}
                  className="flex items-center gap-3.5 px-3 py-2 border cursor-pointer hover:border-[#3A4048] transition-colors"
                >
                  <span className="w-12 flex-shrink-0 font-mono-code text-[12px] text-[#8C949F]">
                    {p.id}
                  </span>
                  <span
                    style={{ color: isRunning ? '#E6E9ED' : p.state === 'COMPLETE' ? '#8C949F' : '#5C646E' }}
                    className="w-16 flex-shrink-0 font-mono-code text-[11px] tracking-wider font-semibold"
                  >
                    {p.phase}
                  </span>
                  <span
                    style={{ color: agentCol }}
                    className="w-24 flex-shrink-0 flex items-center gap-1.5 text-[12px]"
                  >
                    <span
                      style={{ borderColor: agentCol }}
                      className="w-3.5 h-3.5 border flex items-center justify-center font-mono-code text-[10px] clip-hex"
                    >
                      {agentName[0]}
                    </span>
                    {agentName}
                  </span>
                  <span className="flex-1 min-w-0 text-[12px] text-[#B7BEC7] truncate font-sans">
                    {p.task}
                  </span>
                  <span className="w-24 flex-shrink-0 text-right font-mono-code text-[11px] text-[#5C646E]">
                    {p.meta}
                  </span>
                  <span
                    style={{ color: stateCol }}
                    className="w-24 flex-shrink-0 flex items-center justify-end gap-1.5 font-mono-code text-[11px] tracking-wider font-semibold"
                  >
                    <span
                      style={{ backgroundColor: stateCol }}
                      className={`w-1.5 h-1.5 rounded-[1px] ${isRunning && liveMotion ? 'animate-pulse' : ''}`}
                    />
                    {p.state}
                  </span>
                </div>

                {/* Connector Line */}
                {idx < pipeline.length - 1 && (
                  <div
                    style={{
                      backgroundColor: p.state === 'COMPLETE' ? 'rgba(63,185,80,0.4)' : '#1F242B'
                    }}
                    className="h-3 w-[1px] ml-5"
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Main Queue Table */}
      <QueueTable
        jobs={jobs}
        onSelectJob={(id) => setActiveModalJobId(id)}
        showFilters={true}
      />

      <div className="px-5 pt-3.5 font-mono-code text-[11px] text-[#5C646E]">
        estimates from historical medians · confidence varies per row · policy: serial per repository
      </div>
    </div>
  );
};

export default QueueRoute;
