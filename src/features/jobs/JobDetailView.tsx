import React from 'react';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { useJob } from '../../api/hooks';
import { resolveActorRef } from '../../api/mock/actors';

interface JobDetailViewProps {
  jobId?: string;
}

export const JobDetailView: React.FC<JobDetailViewProps> = ({ jobId = '#142' }) => {
  const { elapsed, jobTokens, hardenTokens, allEvents } = useConsoleStore();
  const { job } = useJob(jobId);

  const displayJob = job || {
    id: jobId,
    priority: 'P1' as const,
    title: 'Redis State Migration',
    repository: 'moveinmate/backend',
    branch: 'feat/redis-state',
    status: 'RUNNING' as const,
    assignedAgentIds: ['gemini', 'claude', 'codex'],
    startedAt: '10:38',
    budget: '80k',
    policy: 'serial · retry 3',
    executionGraph: [
      { id: '1', phase: 'BUILD' as const, agentId: 'gemini', agentName: 'Gemini', note: 'implementation complete', meta: '30.4k\n06:12', mark: '✓', state: 'COMPLETE' as const, task: 'Build' },
      { id: '2', phase: 'HARDEN' as const, agentId: 'claude', agentName: 'Claude', note: 'reviewing store contract', meta: `${hardenTokens}\n02:14`, mark: '●', state: 'RUNNING' as const, task: 'Harden' },
      { id: '3', phase: 'VERIFY' as const, agentId: 'codex', agentName: 'Codex', note: 'waiting for handoff', meta: '~19k\n~3m', mark: '○', state: 'QUEUED' as const, task: 'Verify' },
      { id: '4', phase: 'COMPLETE' as const, agentId: 'elysia', agentName: 'Elysia', note: 'merge + report', meta: '', mark: '', state: 'idle' as const, task: 'Complete' }
    ],
    changedFiles: [
      { mark: 'A' as const, path: 'src/state/redis_store.py', add: '+184', del: '−0', byActorId: 'gemini', byDisplayName: 'Gemini' },
      { mark: 'M' as const, path: 'src/state/store.py', add: '+22', del: '−96', byActorId: 'gemini', byDisplayName: 'Gemini' },
      { mark: 'M' as const, path: 'src/state/__init__.py', add: '+4', del: '−2', byActorId: 'gemini', byDisplayName: 'Gemini' },
      { mark: 'A' as const, path: 'tests/state/test_redis_store.py', add: '+141', del: '−0', byActorId: 'gemini', byDisplayName: 'Gemini' },
      { mark: 'M' as const, path: 'tests/state/test_migration.py', add: '+38', del: '−11', byActorId: 'gemini', byDisplayName: 'Gemini' },
      { mark: 'M' as const, path: 'docs/adr/0007-state.md', add: '+61', del: '−4', byActorId: 'claude', byDisplayName: 'Claude' },
      { mark: 'M' as const, path: 'compose.yaml', add: '+9', del: '−0', byActorId: 'gemini', byDisplayName: 'Gemini' }
    ],
    testSummary: {
      passed: 184,
      skipped: 2,
      failed: 0,
      duration: '18.4s',
      rawLog: `tests/state/test_redis_store.py ......... [ 62%]\ntests/state/test_migration.py ....s.... [ 91%]\ntests/state/test_ttl.py ....s [100%]\n186 collected · 184 passed · 2 skipped in 18.4s`
    },
    retryHistory: [
      { attempt: 1, phase: 'BUILD' as const, status: 'failed' as const, note: 'redis connection refused in sandbox; retried with local container' },
      { attempt: 2, phase: 'BUILD' as const, status: 'passed' as const, note: 'container connection successful' }
    ],
    retriesUsed: 1,
    maxRetries: 3,
    tokenBreakdown: [
      { agentId: 'gemini', agentName: 'Gemini', phase: 'BUILD' as const, tokensFormatted: '30.4k', color: '#5B8CFF', percentage: 38 },
      { agentId: 'claude', agentName: 'Claude', phase: 'HARDEN' as const, tokensFormatted: hardenTokens, color: '#D9A05B', percentage: 17 },
      { agentId: 'codex', agentName: 'Codex', phase: 'VERIFY' as const, tokensFormatted: '~19k', color: '#4EC9A0', percentage: 0 }
    ]
  };

  return (
    <div className="w-full bg-[#0A0B0D] select-none">
      {/* Header Banner */}
      <div className="p-5 border-b border-[#1F242B] bg-[#0C0E11]">
        <div className="flex items-center gap-3">
          <span className="font-mono-code text-[22px] text-[#5C646E]">{displayJob.id}</span>
          <h2 className="text-[22px] font-semibold text-[#E6E9ED]">
            {displayJob.title}
          </h2>
          <span className="flex items-center gap-1.5 font-mono-code text-[11px] tracking-wider text-[#3FB950] border border-[rgba(63,185,80,0.35)] px-2 py-0.5 bg-[rgba(63,185,80,0.08)]">
            <span className="w-1 h-1 rounded-[1px] bg-[#3FB950] animate-pulse" />
            {displayJob.status}
          </span>
        </div>

        <div className="mt-2.5 flex items-center flex-wrap gap-x-4 gap-y-1 font-mono-code text-[11px] text-[#8C949F]">
          <span>{displayJob.repository}</span>
          {displayJob.branch && <span className="text-[#CBA35C]">{displayJob.branch}</span>}
          <span className="text-[#2A3038]">·</span>
          <span>started {displayJob.startedAt || '10:38'}</span>
          <span>elapsed <span className="text-[#E6E9ED]">{elapsed}</span></span>
          <span>budget <span className="text-[#E6E9ED]">{jobTokens}</span> / {displayJob.budget || '80k'}</span>
          <span>policy <span className="text-[#E6E9ED]">{displayJob.policy || 'serial · retry 3'}</span></span>
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
              {displayJob.executionGraph.map((g, idx) => {
                const actor = g.agentId ? resolveActorRef(g.agentId) : null;
                const col = actor?.accentColor || '#3A4048';
                const isDone = g.state === 'COMPLETE';
                const isActive = g.state === 'RUNNING';

                return (
                  <div key={g.id || idx}>
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
                        {g.mark || (isDone ? '✓' : isActive ? '●' : '○')}
                      </div>

                      <div className="flex-1 min-w-0">
                        <div
                          style={{ color: isDone || isActive ? '#E6E9ED' : '#5C646E' }}
                          className="font-mono-code text-[11px] tracking-wider font-semibold"
                        >
                          {g.phase}
                        </div>
                        <div style={{ color: g.state === 'idle' ? '#3A4048' : col }} className="text-[12px] mt-0.5">
                          {g.agentName || actor?.displayName || '—'}
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
                    {idx < displayJob.executionGraph.length - 1 && (
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
              {displayJob.tokenBreakdown.map((t, idx) => (
                <div
                  key={idx}
                  style={{
                    width: `${t.percentage || 25}%`,
                    backgroundColor: t.color || '#5B8CFF',
                    opacity: 0.85
                  }}
                  title={`${t.agentName} ${t.phase}: ${t.tokensFormatted}`}
                />
              ))}
            </div>

            <div className="mt-2.5 flex flex-col gap-1.5 font-mono-code text-[11px]">
              {displayJob.tokenBreakdown.map((t, idx) => (
                <div key={idx} className="flex justify-between text-[#8C949F]">
                  <span style={{ color: t.color }}>{t.agentName} · {t.phase}</span>
                  <span>{t.tokensFormatted}</span>
                </div>
              ))}
              <div className="flex justify-between text-[#8C949F] border-t border-[#1F242B] pt-1.5 mt-1">
                <span>total / cap</span>
                <span className="text-[#E6E9ED]">{jobTokens} / {displayJob.budget || '80k'}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Changed Files, Test Results, Tool Calls */}
        <div className="flex-1 min-w-0 flex flex-col">
          {/* Changed Files */}
          <div className="p-4 border-b border-[#1F242B]">
            <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-2.5">
              CHANGED FILES · {displayJob.changedFiles.length}
            </div>
            <div className="flex flex-col gap-1">
              {displayJob.changedFiles.map((f, idx) => {
                const actor = resolveActorRef(f.byActorId);
                return (
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
                      style={{ color: actor.accentColor || '#8C949F' }}
                      className="w-16 text-right font-medium"
                    >
                      {f.byDisplayName || actor.displayName}
                    </span>
                  </div>
                );
              })}
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
                <span className="text-[#3FB950]">{displayJob.testSummary?.passed || 0} passed</span>
                <span className="text-[#E3A008]">{displayJob.testSummary?.skipped || 0} skipped</span>
                <span className="text-[#8C949F]">{displayJob.testSummary?.failed || 0} failed</span>
                <span className="text-[#5C646E]">{displayJob.testSummary?.duration || '—'}</span>
              </div>
              <div className="mt-3 p-3 bg-[#0E1116] border border-[#1F242B] font-mono-code text-[11px] text-[#8C949F] leading-relaxed whitespace-pre">
                {displayJob.testSummary?.rawLog || 'No test logs available.'}
              </div>
            </div>

            {/* Retry History */}
            <div className="w-full md:w-72 p-4">
              <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-2.5">
                RETRY HISTORY
              </div>
              <div className="flex flex-col gap-2 font-mono-code text-[11px]">
                {displayJob.retryHistory.map((r, idx) => (
                  <div key={idx} className="flex flex-col gap-0.5">
                    <div className="flex justify-between text-[#8C949F]">
                      <span>attempt {r.attempt} · {r.phase}</span>
                      <span className={r.status === 'passed' ? 'text-[#3FB950]' : 'text-[#F2555A]'}>{r.status}</span>
                    </div>
                    {r.note && (
                      <div className="text-[#5C646E] text-[10.5px] leading-relaxed">
                        {r.note}
                      </div>
                    )}
                  </div>
                ))}
                <div className="flex justify-between text-[#8C949F] border-t border-[#1F242B] pt-2 mt-1">
                  <span>retries used</span>
                  <span className="text-[#E6E9ED]">{displayJob.retriesUsed} / {displayJob.maxRetries}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Tool Calls */}
          <div className="p-4 pb-8">
            <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-2.5">
              TOOL CALLS · {displayJob.id}
            </div>
            <div className="flex flex-col">
              {allEvents.slice(0, 8).map((e) => (
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
