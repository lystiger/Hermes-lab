import React from 'react';
import { AgentDetail } from '../../api/types';
import { UnknownValue } from '../../components/DataStates';
import { CopyId } from '../../components/CopyId';
import { AgentPortrait } from './AgentPortrait';
import { AgentContextMeter } from './AgentContextMeter';
import { AgentAllowanceCard } from './AgentAllowanceCard';
import { AgentActivityList } from './AgentActivityList';
import { AgentRunsTable } from './AgentRunsTable';
import { AgentMetricsGrid } from './AgentMetricsGrid';
import { MessageDispatcher } from '../messaging/MessageDispatcher';
import { useConsoleStore } from '../../stores/useConsoleStore';

const Spec: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex flex-col gap-0.5 min-w-0">
    <span className="font-mono-code text-[10px] tracking-wider text-[#5C646E]">{label}</span>
    <span className="font-mono-code text-[12px] text-[#E6E9ED] break-words">{children}</span>
  </div>
);

/**
 * Agent dossier (research §5.1). Shows only fields Hermes reports for the agent. Anything else is unknown,
 * with the reason on hover. The tool and permission matrix is not shown because Hermes exposes no such data.
 */
export const AgentDossier: React.FC<{ agent: AgentDetail }> = ({ agent }) => {
  const { setActiveDossierAgent } = useConsoleStore();
  const accentColor = agent.presentation?.accentColor || '#8C949F';
  const isRunning = agent.status === 'RUNNING';
  const hasCharacterCard = Boolean(agent.presentation?.characterCardUrl);

  return (
    <article aria-label={`Dossier for ${agent.displayName}`} className="flex flex-col min-w-0 select-none">
      <header className="p-5 border-b border-[#1F242B] bg-[#0C0E11] flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-[24px] font-semibold text-[#E6E9ED]" style={{ borderLeft: `3px solid ${accentColor}`, paddingLeft: 10 }}>
            {agent.displayName}
          </h2>
          <span
            className={`font-mono-code text-[11px] tracking-wider border px-2 py-0.5 ${isRunning ? 'text-[#3FB950] border-[rgba(63,185,80,0.35)]' : 'text-[#8C949F] border-[#2A3038]'}`}
          >
            {agent.status}
          </span>
          <CopyId value={agent.id} className="text-[#5C646E] text-[11px]" />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled
            title="Operator commands are not available: the Hermes API has no command endpoint yet"
            className="font-mono-code text-[11px] px-2.5 py-1 border border-[#2A3038] text-[#5C646E] cursor-not-allowed"
          >
            dispatch task (unavailable)
          </button>
          {hasCharacterCard && (
            <button
              type="button"
              onClick={() => setActiveDossierAgent(agent)}
              style={{ borderColor: `${accentColor}44`, color: accentColor }}
              className="font-mono-code text-[11px] tracking-wider px-2.5 py-1 border hover:bg-[#161A20] cursor-pointer"
            >
              [ VIEW DOSSIER ]
            </button>
          )}
        </div>
      </header>

      <div className="p-5 grid grid-cols-1 xl:grid-cols-[220px_1fr] gap-6 border-b border-[#1F242B]">
        <div className="flex flex-col items-center xl:items-start gap-2">
          <AgentPortrait
            displayName={agent.displayName}
            presentation={agent.presentation}
            status={agent.status}
            phase={agent.phase}
            crawlCode={agent.crawlCode}
            size="lg"
          />
        </div>

        <div className="flex flex-col gap-5 min-w-0">
          <section aria-label="Core specs" className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <Spec label="PROVIDER">{agent.provider || <UnknownValue reason="Not reported by Hermes" />}</Spec>
            <Spec label="MODEL">{agent.model || <UnknownValue reason="Not reported by Hermes" />}</Spec>
            <Spec label="ROLE">{agent.role || <UnknownValue reason="Not reported by Hermes" />}</Spec>
            <Spec label="PHASE">{agent.phase || <UnknownValue reason="Hermes reports no phase for this agent" />}</Spec>
            <Spec label="CURRENT TASK">
              {agent.currentTask || <UnknownValue reason="Hermes reports no current task for this agent" />}
            </Spec>
            <Spec label="ACTIVE TOOL">
              {agent.activeTool || <UnknownValue reason="Hermes reports no active tool for this agent" />}
            </Spec>
          </section>

          <section aria-label="Capabilities" className="flex flex-col gap-2">
            <span className="font-mono-code text-[10px] tracking-wider text-[#5C646E]">CAPABILITIES</span>
            {agent.capabilities.length === 0 ? (
              <span className="font-mono-code text-[11px] text-[#5C646E]">none reported</span>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {agent.capabilities.map((cap) => (
                  <span key={cap} className="font-mono-code text-[10px] px-1.5 py-0.5 bg-[#141820] border border-[#242A36] text-[#A5D6FF]">
                    {cap}
                  </span>
                ))}
              </div>
            )}
          </section>

          <section aria-label="Context window" className="max-w-md">
            <AgentContextMeter agent={agent} />
          </section>
        </div>
      </div>

      <div className="p-5 border-b border-[#1F242B] flex flex-wrap gap-6">
        <AgentActivityList agent={agent} />
        <AgentAllowanceCard agent={agent} />
      </div>

      <AgentMetricsGrid agent={agent} />
      <AgentRunsTable agent={agent} />

      <div className="p-5 border-t border-[#1F242B] bg-[#0C0E11]">
        <MessageDispatcher />
      </div>
    </article>
  );
};
