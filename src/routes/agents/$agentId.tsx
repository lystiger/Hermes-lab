import React, { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { AgentPortrait } from '../../features/agents/AgentPortrait';
import { AgentContextMeter } from '../../features/agents/AgentContextMeter';
import { AgentActivityList } from '../../features/agents/AgentActivityList';
import { AgentAllowanceCard } from '../../features/agents/AgentAllowanceCard';
import { AgentMetricsGrid } from '../../features/agents/AgentMetricsGrid';
import { AgentRunsTable } from '../../features/agents/AgentRunsTable';
import { MessageDispatcher } from '../../features/messaging/MessageDispatcher';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { AGENTS_MAP } from '../../api/mockData';

export const AgentDetailRoute: React.FC = () => {
  const { agentId } = useParams<{ agentId: string }>();
  const navigate = useNavigate();
  const { setSelectedAgentId } = useConsoleStore();

  const activeKey = Object.keys(AGENTS_MAP).find(
    (k) => k.toLowerCase() === (agentId || '').toLowerCase()
  );
  const agent = activeKey ? AGENTS_MAP[activeKey] : AGENTS_MAP.Claude;

  useEffect(() => {
    if (agentId) {
      setSelectedAgentId(agentId);
    }
  }, [agentId, setSelectedAgentId]);

  const isRunning = agent.status === 'RUNNING';

  return (
    <div className="flex flex-col select-none bg-[#0A0B0D]">
      {/* Top Hero Section */}
      <div className="flex flex-col xl:flex-row gap-6 p-5 border-b border-[#1F242B] bg-[#0C0E11]">
        {/* Left 3D Large Portrait Showcase */}
        <div className="flex flex-col items-center xl:items-start flex-shrink-0">
          <AgentPortrait agent={agent} size="lg" />
          <div className="mt-2.5 w-full flex justify-between font-mono-code text-[11px] text-[#5C646E]">
            <span>{agent.model}</span>
            <span style={{ color: agent.color }}>{agent.traceId}</span>
          </div>
        </div>

        {/* Right Info and Breakdown */}
        <div className="flex-1 min-w-0 flex flex-col">
          {/* Header Title & Status */}
          <div className="flex items-center gap-3">
            <h2 className="text-[26px] font-semibold text-[#E6E9ED]">
              {agent.name}
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
