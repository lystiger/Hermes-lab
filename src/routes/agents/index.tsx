import React from 'react';
import { AgentLaneCard } from '../../features/agents/AgentLaneCard';
import { MessageDispatcher } from '../../features/messaging/MessageDispatcher';
import { useAgents } from '../../api/hooks';

export const AgentsListRoute: React.FC = () => {
  const { agents, loading } = useAgents();

  return (
    <div className="flex flex-col select-none bg-[#0A0B0D]">
      {/* Tactical Dispatch Bar */}
      <div className="p-5 border-b border-[#1F242B] bg-[#0C0E11]">
        <MessageDispatcher />
      </div>

      {/* Agents Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-2 gap-0 border-b border-[#1F242B]">
        {agents.map((ag) => (
          <AgentLaneCard key={ag.id} agent={ag} size="full" />
        ))}
      </div>

      {loading && (
        <div className="p-8 text-center font-mono-code text-[12px] text-[#5C646E]">
          Loading operator registry...
        </div>
      )}

      <div className="p-5 font-mono-code text-[11px] text-[#5C646E]">
        Operator configuration loaded from <span className="text-[#8C949F]">~/.lyscontrol/agents.toml</span> · Click any operator to inspect metrics, context window allocations, and trace history.
      </div>
    </div>
  );
};

export default AgentsListRoute;
