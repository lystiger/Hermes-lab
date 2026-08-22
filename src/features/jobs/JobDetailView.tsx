import React from 'react';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { AGENT_COLOR_MAP } from '../../api/mockData';

export const JobDetailView: React.FC = () => {
  const { elapsed, jobTokens, hardenTokens, changedFiles, allEvents } = useConsoleStore();

  const graphSteps = [
    { phase: 'BUILD', agent: 'Gemini', note: 'implementation complete', meta: '30.4k\n06:12', mark: '✓', state: 'done' },
    { phase: 'HARDEN', agent: 'Claude', note: 'reviewing store contract', meta: `${hardenTokens}\n02:14`, mark: '●', state: 'active' },
    { phase: 'VERIFY', agent: 'Codex', note: 'waiting for handoff', meta: '~19k\n~3m', mark: '○', state: 'next' },
    { phase: 'COMPLETE', agent: 'Elysia', note: 'merge + report', meta: '', mark: '', state: 'idle' }
  ];

  const testLog = `tests/state/test_redis_store.py ......... [ 62%]
tests/state/test_migration.py ....s.... [ 91%]
tests/state/test_ttl.py ....s [100%]
186 collected · 184 passed · 2 skipped in 18.4s`;

  return (
    <div className="w-full bg-[#0A0B0D] select-none">
      {/* Header Banner */}
      <div className="p-5 border-b border-[#1F242B] bg-[#0C0E11]">
        <div className="flex items-center gap-3">
          <span className="font-mono-code text-[22px] text-[#5C646E]">#142</span>
          <h2 className="text-[22px] font-semibold text-[#E6E9ED]">
            Redis State Migration
          </h2>
          <span className="flex items-center gap-1.5 font-mono-code text-[11px] tracking-wider text-[#3FB950] border border-[rgba(63,185,80,0.35)] px-2 py-0.5 bg-[rgba(63,185,80,0.08)]">
            <span className="w-1 h-1 rounded-[1px] bg-[#3FB950] animate-pulse" />
            RUNNING
          </span>
        </div>

        <div className="mt-2.5 flex items-center flex-wrap gap-x-4 gap-y-1 font-mono-code text-[11px] text-[#8C949F]">
          <span>moveinmate/backend</span>
          <span className="text-[#CBA35C]">feat/redis-state</span>
          <span className="text-[#2A3038]">·</span>
          <span>started 10:38</span>
          <span>elapsed <span className="text-[#E6E9ED]">{elapsed}</span></span>
          <span>budget <span className="text-[#E6E9ED]">{jobTokens}</span> / 80k</span>
          <span>policy <span className="text-[#E6E9ED]">serial · retry 3</span></span>
        </div>
      </div>

      {/* Main Body Split */}
      <div className="flex flex-col lg:flex-row items-stretch">
        {/* Left Column: Execution Graph & Token consumption */}
        <div className="w-full lg:w-80 flex-shrink-0 border-r border-b lg:border-b-0 border-[#1F242B] p-5 bg-[#0A0B0D]">
          <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-4">
            EXECUTION GRAPH
          </div>

          <div style={{ perspective: '800px' }} className="flex flex-col">
            <div style={{ transformStyle: 'preserve-3d' }} className="flex flex-col">
              {graphSteps.map((g, idx) => {
                const col = AGENT_COLOR_MAP[g.agent] || '#3A4048';
                const isDone = g.state === 'done';
                const isActive = g.state === 'active';

                return (
                  <div key={idx}>
                    <div
                      style={{
                        borderColor: isActive ? 'rgba(217,160,91,0.45)' : isDone ? '#1F242B' : '#161A1F',
                        backgroundColor: isActive ? 'rgba(217,160,91,0.06)' : isDone ? '#0E1116' : 'transparent',
                        transform: isActive ? 'translateZ(18px) rotateX(2deg)' : 'translateZ(0)',
                        boxShadow: isActive ? '0 14px 26px -14px rgba(217,160,91,0.55)' : 'none'
                      }}
                      className="flex gap-3 items-start p-3 border"
                    >
                      {/* Mark Icon */}
                      <div
                        style={{
                          borderColor: isDone ? 'rgba(63,185,80,0.6)' : isActive ? col : '#2A3038',
                          backgroundColor: isDone ? 'rgba(63,185,80,0.14)' : 'transparent',
                          color: isDone ? '#3FB950' : isActive ? col : '#3A4048'
                        }}
                        className="w-4.5 h-4.5 flex-shrink-0 flex items-center justify-center font-mono-code text-[11px] clip-hex"
                      >
                        {g.mark}
                      </div>

                      <div className="flex-1 min-w-0">
                        <div
                          style={{ color: isDone || isActive ? '#E6E9ED' : '#5C646E' }}
                          className="font-mono-code text-[11px] tracking-wider font-semibold"
                        >
                          {g.phase}
                        </div>
                        <div style={{ color: g.state === 'idle' ? '#3A4048' : col }} className="text-[12px] mt-0.5">
                          {g.agent}
                        </div>
                        <div className="font-mono-code text-[11px] text-[#5C646E] mt-0.5">
                          {g.note}
                        </div>
                      </div>

                      <div className="font-mono-code text-[11px] text-[#5C646E] text-right whitespace-pre">
                        {g.meta}
                      </div>
                    </div>

                    {/* Step Connector */}
                    {idx < graphSteps.length - 1 && (
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

          {/* Token Consumption */}
          <div className="mt-5 pt-3.5 border-t border-[#1F242B]">
            <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-2.5">
              TOKEN CONSUMPTION
            </div>
            <div className="flex h-2.5 bg-[#14171C] overflow-hidden">
              <div className="w-[38%] bg-[#5B8CFF] opacity-85" title="Gemini BUILD: 30.4k" />
              <div className="w-[17%] bg-[#D9A05B] opacity-85" title="Claude HARDEN: 13.7k" />
              <div className="w-[0%] bg-[#4EC9A0] opacity-85" title="Codex VERIFY: pending" />
            </div>

            <div className="mt-2.5 flex flex-col gap-1.5 font-mono-code text-[11px]">
              <div className="flex justify-between text-[#8C949F]">
                <span className="text-[#5B8CFF]">Gemini · BUILD</span>
                <span>30.4k</span>
              </div>
              <div className="flex justify-between text-[#8C949F]">
                <span className="text-[#D9A05B]">Claude · HARDEN</span>
                <span>{hardenTokens}</span>
              </div>
              <div className="flex justify-between text-[#8C949F]">
                <span className="text-[#4EC9A0]">Codex · VERIFY</span>
                <span>pending ~19k</span>
              </div>
              <div className="flex justify-between text-[#8C949F] border-t border-[#1F242B] pt-1.5 mt-1">
                <span>total / cap</span>
                <span className="text-[#E6E9ED]">{jobTokens} / 80k</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Changed Files, Test Results, Tool Calls */}
        <div className="flex-1 min-w-0 flex flex-col">
          {/* Changed Files */}
          <div className="p-4 border-b border-[#1F242B]">
            <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-2.5">
              CHANGED FILES · {changedFiles.length}
            </div>
            <div className="flex flex-col gap-1">
              {changedFiles.map((f, idx) => (
                <div
                  key={idx}
                  className="flex items-center gap-3.5 py-1 font-mono-code text-[11.5px] hover:bg-[#12151A] px-1"
                >
                  <span
                    style={{ color: f.mark === 'A' ? '#3FB950' : '#E3A008' }}
                    className="w-4 font-bold"
                  >
                    {f.mark}
                  </span>
                  <span className="flex-1 min-w-0 text-[#D7DCE2] truncate">
                    {f.path}
                  </span>
                  <span className="w-14 text-right text-[#3FB950]">{f.add}</span>
                  <span className="w-12 text-right text-[#F2555A]">{f.del}</span>
                  <span
                    style={{ color: AGENT_COLOR_MAP[f.by] }}
                    className="w-16 text-right font-medium"
                  >
                    {f.by}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Test Results & Retry History */}
          <div className="flex flex-col md:flex-row border-b border-[#1F242B]">
            {/* Test Results */}
            <div className="flex-1 p-4 border-b md:border-b-0 md:border-r border-[#1F242B]">
              <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-2.5">
                TEST RESULTS
              </div>
              <div className="flex gap-5 font-mono-code text-[12px]">
                <span className="text-[#3FB950]">184 passed</span>
                <span className="text-[#E3A008]">2 skipped</span>
                <span className="text-[#8C949F]">0 failed</span>
                <span className="text-[#5C646E]">18.4s</span>
              </div>
              <div className="mt-3 p-3 bg-[#0E1116] border border-[#1F242B] font-mono-code text-[11px] text-[#8C949F] leading-relaxed whitespace-pre">
                {testLog}
              </div>
            </div>

            {/* Retry History */}
            <div className="w-full md:w-72 p-4">
              <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-2.5">
                RETRY HISTORY
              </div>
              <div className="flex flex-col gap-2 font-mono-code text-[11px]">
                <div className="flex justify-between text-[#8C949F]">
                  <span>attempt 1 · BUILD</span>
                  <span className="text-[#F2555A]">failed</span>
                </div>
                <div className="text-[#5C646E] text-[10.5px] leading-relaxed">
                  redis connection refused in sandbox; retried with local container
                </div>
                <div className="flex justify-between text-[#8C949F] border-t border-[#1F242B] pt-2">
                  <span>attempt 2 · BUILD</span>
                  <span className="text-[#3FB950]">passed</span>
                </div>
                <div className="flex justify-between text-[#8C949F]">
                  <span>retries used</span>
                  <span className="text-[#E6E9ED]">1 / 3</span>
                </div>
              </div>
            </div>
          </div>

          {/* Tool Calls */}
          <div className="p-4 pb-8">
            <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-2.5">
              TOOL CALLS · JOB #142
            </div>
            <div className="flex flex-col">
              {allEvents.slice(0, 8).map((e, idx) => (
                <div
                  key={idx}
                  className="flex items-center gap-3.5 py-1 font-mono-code text-[11px] border-b border-[#101216]"
                >
                  <span className="w-24 text-[#5C646E]">{e.ts}</span>
                  <span
                    style={{ color: AGENT_COLOR_MAP[e.agent] || '#8C949F' }}
                    className="w-16 font-medium"
                  >
                    {e.agent}
                  </span>
                  <span className="w-28 text-[#8C949F]">{e.kind}</span>
                  <span className="flex-1 min-w-0 text-[#B7BEC7] truncate">{e.detail}</span>
                  <span className="w-16 text-right text-[#8C949F]">{e.dur}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
