import React from 'react';
import { AgentLaneCard } from '../../features/agents/AgentLaneCard';
import { MessageDispatcher } from '../../features/messaging/MessageDispatcher';
import { useAgents } from '../../api/hooks';
import { EmptyState, ErrorState, Freshness, LoadingState } from '../../components/DataStates';

export const AgentsListRoute: React.FC = () => {
  const { agents, loading, error, updatedAt, refetch } = useAgents();

  return (
    <div className="flex flex-col select-none bg-[#0A0B0D]">
      {/* Tactical Dispatch Bar */}
      <div className="p-5 border-b border-[#1F242B] bg-[#0C0E11]">
        <MessageDispatcher />
      </div>

      {loading && agents.length === 0 && <LoadingState label="Loading operator registry…" />}
      {error && agents.length === 0 && <ErrorState label="Operator registry" error={error} onRetry={refetch} />}
      {!loading && !error && agents.length === 0 && <EmptyState>Hermes reports no registered agents.</EmptyState>}

      {/* Agents Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-2 gap-0 border-b border-[#1F242B]">
        {agents.map((ag) => (
          <AgentLaneCard key={ag.id} agent={ag} size="full" />
        ))}
      </div>

      <div className="p-5 flex flex-wrap items-center gap-x-4 font-mono-code text-[11px] text-[#5C646E]">
        <span>
          Operators are reported by Hermes (GET /agents). Click an operator to inspect its identity and status.
        </span>
        <Freshness at={updatedAt} />
      </div>
    </div>
  );
};

export default AgentsListRoute;
