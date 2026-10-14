import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAgent, useAgents } from '../../api/hooks';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { EmptyState, ErrorState, LoadingState } from '../../components/DataStates';
import { AgentRoster } from './AgentRoster';
import { AgentDossier } from './AgentDossier';

/**
 * Roster on the left, dossier of the selected agent on the right (research §5.1). The route decides the
 * selection: /agents picks the first agent, /agents/:id picks that agent.
 */
export const AgentWorkspace: React.FC<{ selectedId?: string }> = ({ selectedId }) => {
  const navigate = useNavigate();
  const { setSelectedAgentId } = useConsoleStore();
  const roster = useAgents();
  const [filter, setFilter] = useState('ALL');

  const effectiveId = selectedId ?? roster.agents[0]?.id ?? null;
  const detail = useAgent(effectiveId ?? undefined);

  useEffect(() => {
    if (effectiveId) setSelectedAgentId(effectiveId);
  }, [effectiveId, setSelectedAgentId]);

  return (
    <div className="flex flex-col md:flex-row min-h-0 bg-[#0A0B0D]">
      <AgentRoster
        agents={roster.agents}
        selectedId={effectiveId}
        filter={filter}
        onFilter={setFilter}
        onSelect={(id) => navigate(`/agents/${id}`)}
        loading={roster.loading}
        error={roster.error}
        updatedAt={roster.updatedAt}
        onRetry={roster.refetch}
      />

      <div className="flex-1 min-w-0">
        {!effectiveId && !roster.loading && !roster.error && (
          <EmptyState>Select an agent once Hermes reports one.</EmptyState>
        )}
        {effectiveId && detail.loading && !detail.agent && <LoadingState label={`Loading ${effectiveId}…`} />}
        {effectiveId && detail.error && !detail.agent && (
          <ErrorState label={`Agent ${effectiveId}`} error={detail.error} onRetry={detail.refetch} />
        )}
        {effectiveId && !detail.loading && !detail.error && !detail.agent && (
          <EmptyState>Agent {effectiveId} is not in the Hermes registry.</EmptyState>
        )}
        {detail.agent && <AgentDossier agent={detail.agent} />}
      </div>
    </div>
  );
};
