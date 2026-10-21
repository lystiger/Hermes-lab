import React from 'react';
import { useAgentModels, useAgents } from '../../api/hooks';
import { AgentModelConfig } from '../../api/types';
import { EmptyState, ErrorState, LoadingState, StaleNotice } from '../../components/DataStates';
import { PageHeader, HeaderCount } from '../../components/PageHeader';

/** The model an agent runs on: the configured default, else the last model used, else unknown. */
function modelOf(config?: AgentModelConfig): string {
  return config?.configured?.default ?? config?.lastUsed?.model ?? '—';
}

/** The reasoning effort: the configured one, else the last one used, else unknown. */
function reasoningOf(config?: AgentModelConfig): string {
  return config?.configured?.effort ?? config?.lastUsed?.effort ?? '—';
}

/** /agents: a plain list of agents with their model and reasoning effort. No art, no dossier. */
export const AgentsListRoute: React.FC = () => {
  const { agents, loading, error, refetch, updatedAt, stale } = useAgents();
  const { models, loading: modelsLoading, error: modelsError, refetch: refetchModels, updatedAt: modelsUpdatedAt } = useAgentModels();

  const counts: HeaderCount[] = [{ label: 'agents', value: agents.length }];
  const failed = error ?? modelsError;
  const retry = () => {
    refetch();
    refetchModels();
  };

  return (
    <>
      <PageHeader title="Agents" counts={counts} updatedAt={updatedAt ?? modelsUpdatedAt} />
      <section className="p-6">
        {stale && <StaleNotice label="Agents" error={error} onRetry={retry} />}
        {failed && agents.length === 0 && <ErrorState label="Agents" error={failed} onRetry={retry} />}
        {loading && agents.length === 0 && <LoadingState label="Loading agents" />}
        {!loading && !failed && agents.length === 0 && <EmptyState>No agents</EmptyState>}
        {agents.length > 0 && (
          <table className="w-full text-left font-sans text-[13px] text-lys-primary">
            <thead className="text-[11px] uppercase tracking-wider text-lys-faint">
              <tr>
                <th scope="col" className="py-2 pr-4 font-medium">Agent</th>
                <th scope="col" className="py-2 pr-4 font-medium">Provider</th>
                <th scope="col" className="py-2 pr-4 font-medium">Model</th>
                <th scope="col" className="py-2 pr-4 font-medium">Reasoning</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => {
                const config = models?.[agent.id];
                return (
                  <tr key={agent.id} className="border-t border-lys-subtle">
                    <td className="py-2 pr-4">{agent.displayName}</td>
                    <td className="py-2 pr-4 text-lys-muted">{agent.provider}</td>
                    <td className="py-2 pr-4">{modelOf(config)}</td>
                    <td className="py-2 pr-4">{reasoningOf(config)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {modelsLoading && models === null && agents.length > 0 && <LoadingState label="Loading models" />}
      </section>
    </>
  );
};

export default AgentsListRoute;
