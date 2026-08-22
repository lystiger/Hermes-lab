import React from 'react';
import { useConsoleStore } from '../stores/useConsoleStore';
import { AGENT_COLOR_MAP } from '../api/mockData';

export const EventsRoute: React.FC = () => {
  const { events, eFilter, setEFilter, allEvents, setActiveModalJobId, liveMotion } = useConsoleStore();

  const filterTabs = ['All', 'Hermes', 'Gemini', 'Claude', 'Codex', 'Errors', 'Tools'];

  const getKindColor = (k: string) => {
    if (k === 'error') return '#F2555A';
    if (k === 'retry' || k === 'quota.warn') return '#E3A008';
    if (k.startsWith('agent.')) return '#3FB950';
    if (k === 'job.start' || k === 'phase.change') return '#CBA35C';
    return '#8C949F';
  };

  const getRowBg = (k: string) => {
    if (k === 'error') return 'rgba(242,85,90,0.07)';
    if (k === 'retry' || k === 'quota.warn') return 'rgba(227,160,8,0.05)';
    return 'transparent';
  };

  return (
    <div className="flex flex-col select-none bg-[#0A0B0D]">
      {/* Sticky Filter Header */}
      <div className="sticky top-0 z-20 flex items-center justify-between px-5 py-2.5 border-b border-[#1F242B] bg-[#0A0B0D]">
        <div className="flex gap-1">
          {filterTabs.map((f) => {
            const isActive = eFilter === f;
            return (
              <button
                key={f}
                onClick={() => setEFilter(f)}
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

        <div className="flex items-center gap-3.5 font-mono-code text-[11px] text-[#5C646E]">
          <span>{allEvents.length} events logged</span>
          <span className="flex items-center gap-1.5 text-[#3FB950]">
            <span className={`w-1.5 h-1.5 rounded-[1px] bg-[#3FB950] ${liveMotion ? 'animate-pulse' : ''}`} />
            streaming
          </span>
        </div>
      </div>

      {/* Table Header */}
      <div className="flex items-center gap-4 px-5 py-2 border-b border-[#1F242B] font-mono-code text-[11px] tracking-wider text-[#5C646E] bg-[#0C0E11]">
        <span className="w-24 flex-shrink-0">TIMESTAMP</span>
        <span className="w-20 flex-shrink-0">SOURCE</span>
        <span className="w-32 flex-shrink-0">EVENT</span>
        <span className="flex-1 min-w-[200px]">DETAIL</span>
        <span className="w-20 flex-shrink-0 text-right">DURATION</span>
        <span className="w-16 flex-shrink-0 text-right">JOB</span>
      </div>

      {/* Event Rows */}
      <div className="flex flex-col">
        {events.map((e) => {
          const agColor = AGENT_COLOR_MAP[e.agent] || '#8C949F';

          return (
            <div
              key={e.id}
              style={{ backgroundColor: getRowBg(e.kind) }}
              className="flex items-center gap-4 px-5 py-1.5 font-mono-code text-[11.5px] border-b border-[#101216] hover:bg-[#12151A] transition-colors"
            >
              <span className="w-24 flex-shrink-0 text-[#5C646E]">{e.ts}</span>
              <span style={{ color: agColor }} className="w-20 flex-shrink-0 font-semibold">
                {e.agent}
              </span>
              <span style={{ color: getKindColor(e.kind) }} className="w-32 flex-shrink-0 font-medium">
                {e.kind}
              </span>
              <span className="flex-1 min-w-[200px] text-[#B7BEC7] truncate font-sans">
                {e.detail}
              </span>
              <span className="w-20 flex-shrink-0 text-right text-[#8C949F]">{e.dur}</span>
              <button
                onClick={() => setActiveModalJobId(e.job)}
                className="w-16 flex-shrink-0 text-right text-[#CBA35C] hover:underline cursor-pointer"
              >
                {e.job}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default EventsRoute;
