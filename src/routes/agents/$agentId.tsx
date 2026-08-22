import React, { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { AgentPortrait } from '../../features/agents/AgentPortrait';
import { AgentContextMeter } from '../../features/agents/AgentContextMeter';
import { AgentActivityList } from '../../features/agents/AgentActivityList';
import { AgentAllowanceCard } from '../../features/agents/AgentAllowanceCard';
import { AgentMetricsGrid } from '../../features/agents/AgentMetricsGrid';
import { AgentRunsTable } from '../../features/agents/AgentRunsTable';
import { MessageDispatcher } from '../../features/messaging/MessageDispatcher';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { useAgent } from '../../api/hooks';

export const AgentDetailRoute: React.FC = () => {
  const { agentId } = useParams<{ agentId: string }>();
  const { setSelectedAgentId, setActiveDossierAgent } = useConsoleStore();
  const { agent, loading } = useAgent(agentId);

  useEffect(() => {
    if (agentId) {
      setSelectedAgentId(agentId);
    }
  }, [agentId, setSelectedAgentId]);

  if (loading && !agent) {
    return (
      <div className="p-8 text-center font-mono-code text-[12px] text-[#5C646E]">
        Loading agent details for [{agentId}]...
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="p-8 text-center font-mono-code text-[12px] text-[#E3A008]">
        Agent [{agentId}] not found in registry.
      </div>
    );
  }

  const isRunning = agent.status === 'RUNNING';
  const accentColor = agent.presentation?.accentColor || '#8C949F';
  const hasCharacterCard = Boolean(agent.presentation?.characterCardUrl);

  return (
    <div className="flex flex-col select-none bg-[#0A0B0D]">
      {/* Top Hero Section */}
      <div className="flex flex-col xl:flex-row gap-6 p-5 border-b border-[#1F242B] bg-[#0C0E11]">
        {/* Left 3D Large Portrait Showcase */}
        <div className="flex flex-col items-center xl:items-start flex-shrink-0">
          <AgentPortrait
            displayName={agent.displayName}
            presentation={agent.presentation}
            status={agent.status}
            phase={agent.phase}
            crawlCode={agent.crawlCode}
            size="lg"
          />
          <div className="mt-2.5 w-full flex justify-between items-center font-mono-code text-[11px] text-[#5C646E]">
            <span>{agent.model}</span>
            <span style={{ color: accentColor }}>{agent.traceId || `trc ${agent.id}·active`}</span>
          </div>

          {/* Optional Restrained Dossier Trigger */}
          {hasCharacterCard && (
            <button
              onClick={() => setActiveDossierAgent(agent)}
              style={{
                borderColor: `${accentColor}44`,
                color: accentColor
              }}
              className="mt-2.5 w-full py-1 text-center font-mono-code text-[11px] tracking-wider border hover:bg-[#161A20] cursor-pointer transition-colors"
            >
              [ VIEW DOSSIER ]
            </button>
          )}
        </div>

        {/* Right Info and Breakdown */}
        <div className="flex-1 min-w-0 flex flex-col">
          {/* Header Title & Status */}
          <div className="flex items-center gap-3">
            <h2 className="text-[26px] font-semibold text-[#E6E9ED]">
              {agent.displayName}
            </h2>
            <span
              style={{
                color: isRunning ? '#3FB950' : '#8C949F',
                borderColor: isRunning ? 'rgba(63,185,80,0.35)' : '#2A3038'
              }}
              className="flex items-center gap-1.5 font-mono-code text-[11px] tracking-wider border px-2 py-0.5"
            >
              <span
                style={{ backgroundColor: isRunning ? '#3FB950' : '#8C949F' }}
                className="w-1 h-1 rounded-[1px]"
              />
              {agent.status}
            </span>
          </div>

          <div className="mt-1.5 font-mono-code text-[11px] text-[#8C949F]">
            {agent.model} · {agent.provider} · {agent.role}
          </div>

          {/* Capabilities Badges (Phase 7) */}
          {agent.capabilities && agent.capabilities.length > 0 && (
            <div className="mt-2.5 flex flex-wrap items-center gap-1.5 font-mono-code text-[10px]">
              <span className="text-[#5C646E]">CAPABILITIES:</span>
              {agent.capabilities.map((cap) => (
                <span
                  key={cap}
                  className="px-1.5 py-0.5 bg-[#141820] border border-[#242A36] text-[#A5D6FF] tracking-wide"
                >
                  {cap}
                </span>
              ))}
            </div>
          )}

          {/* Context, Activity, Allowance 3-column row */}
          <div className="mt-5 flex flex-wrap gap-6">
            <AgentContextMeter agent={agent} />
            <AgentActivityList agent={agent} />
            <AgentAllowanceCard agent={agent} />
          </div>
        </div>
      </div>

      {/* Metrics Row */}
      <AgentMetricsGrid agent={agent} />

      {/* Recent Runs Table */}
      <AgentRunsTable agent={agent} />

      {/* Interactive Command Dispatcher */}
      <div className="p-5 border-t border-[#1F242B] bg-[#0C0E11]">
        <MessageDispatcher />
      </div>
    </div>
  );
};

export default AgentDetailRoute;
