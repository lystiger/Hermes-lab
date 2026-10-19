import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAgent, useAgents } from '../../api/hooks';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { EmptyState, ErrorState, LoadingState, ResourceError } from '../../components/DataStates';
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
    <div className="flex flex-col lg:flex-row min-h-full bg-lys-base">
      <AgentRoster
        agents={roster.agents}
        selectedId={effectiveId}
        filter={filter}
        onFilter={setFilter}
        onSelect={(id) => navigate(`/agents/${id}`)}
        loading={roster.loading}
        error={roster.error}
        stale={roster.stale}
        updatedAt={roster.updatedAt}
        onRetry={roster.refetch}
      />

      <div className="flex-1 min-w-0 flex flex-col">
        {!effectiveId && !roster.loading && !roster.error && (
          <EmptyState>No agent selected</EmptyState>
        )}
        {effectiveId && detail.loading && !detail.agent && <LoadingState label={`Loading ${effectiveId}…`} />}
        {effectiveId && detail.error && !detail.agent && (
          <ErrorState label={`Agent ${effectiveId}`} error={detail.error} onRetry={detail.refetch} />
        )}
        {effectiveId && !detail.loading && !detail.error && !detail.agent && (
          <EmptyState>Agent not found</EmptyState>
        )}
        {detail.agent && detail.stale && (
          <div className="p-3">
            <ResourceError label={`Agent ${detail.agent.displayName}`} error={detail.error} hasData updatedAt={detail.updatedAt} onRetry={detail.refetch} />
          </div>
        )}
        {detail.agent && <AgentDossier agent={detail.agent} updatedAt={detail.updatedAt} />}
      </div>
    </div>
  );
};
