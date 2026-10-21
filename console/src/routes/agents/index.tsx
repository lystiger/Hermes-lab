import React, { useState } from 'react';
import { hermesApi, isMockMode } from '../../api/client';
import { useAgentModels, useAgents } from '../../api/hooks';
import { AgentModelConfig, AgentSummary } from '../../api/types';
import { getValidEffortOptions } from '../../features/agents/AgentModelSelector';
import { EmptyState, ErrorState, LoadingState, StaleNotice } from '../../components/DataStates';
import { PageHeader, HeaderCount } from '../../components/PageHeader';

/** The model an agent runs on: the configured default, else the last model used, else unknown. */
function modelOf(config?: AgentModelConfig): string {
  return config?.configured?.default ?? config?.lastUsed?.model ?? '—';
}

const SELECT_CLASS =
  'px-2 py-1 bg-lys-surface-0 border border-lys-default text-lys-primary font-mono-code text-[12px] rounded-sm focus:outline-none focus:border-lys-strong disabled:opacity-50';

interface AgentRowProps {
  agent: AgentSummary;
  config?: AgentModelConfig;
  onSaved: () => void;
}

/** One agent: its provider, and a model and effort picker that saves to the next phase. */
const AgentRow: React.FC<AgentRowProps> = ({ agent, config, onSaved }) => {
  const [userModel, setUserModel] = useState<string | null>(null);
  const [userEffort, setUserEffort] = useState<string | null | undefined>(undefined);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<unknown | null>(null);

  const allowed = config?.allowed ?? [];
  const effortOptions = getValidEffortOptions(agent.id);
  const baselineModel = modelOf(config) === '—' ? '' : modelOf(config);
  const baselineEffort = config?.configured?.effort ?? null;
  const currentModel = userModel ?? baselineModel;
  const currentEffort = userEffort !== undefined ? userEffort : baselineEffort;
  const changed = currentModel !== baselineModel || currentEffort !== baselineEffort;
  const canSave = !isMockMode && !saving && changed && allowed.includes(currentModel);
  const canPick = !isMockMode && !saving && allowed.length > 0;

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await hermesApi.setAgentModel(agent.id, currentModel, currentEffort);
      setUserModel(null);
      setUserEffort(undefined);
      onSaved();
    } catch (err) {
      setSaveError(err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <tr className="border-t border-lys-subtle align-top">
      <td className="py-2 pr-4">{agent.displayName}</td>
      <td className="py-2 pr-4 text-lys-muted">{agent.provider}</td>
      <td className="py-2 pr-4">
        <select
          aria-label={`Model for ${agent.displayName}`}
          className={SELECT_CLASS}
          value={currentModel}
          disabled={!canPick}
          onChange={(e) => {
            setUserModel(e.target.value);
            setSaveError(null);
          }}
        >
          {!allowed.includes(currentModel) && <option value="" disabled hidden>—</option>}
          {allowed.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </td>
      <td className="py-2 pr-4">
        <select
          aria-label={`Reasoning for ${agent.displayName}`}
          className={SELECT_CLASS}
          value={currentEffort ?? ''}
          disabled={!canPick || effortOptions.length <= 1}
          onChange={(e) => {
            setUserEffort(e.target.value === '' ? null : e.target.value);
            setSaveError(null);
          }}
        >
          {effortOptions.map((eff) => (
            <option key={eff ?? 'null'} value={eff ?? ''}>{eff ?? '—'}</option>
          ))}
        </select>
      </td>
      <td className="py-2 pr-4">
        <button
          type="button"
          onClick={save}
          disabled={!canSave}
          className="text-[12px] px-2.5 py-1 border border-lys-default rounded-sm text-lys-primary disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        {saveError ? <div className="mt-1"><ErrorState label="Model update" error={saveError} onRetry={save} /></div> : null}
      </td>
    </tr>
  );
};

/** /agents: a plain list of agents with their provider, model and reasoning effort, and a picker to change them. */
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
                <th scope="col" className="py-2 pr-4 font-medium"><span className="sr-only">Save</span></th>
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => (
                <AgentRow key={agent.id} agent={agent} config={models?.[agent.id]} onSaved={refetchModels} />
              ))}
            </tbody>
          </table>
        )}
        {modelsLoading && models === null && agents.length > 0 && <LoadingState label="Loading models" />}
      </section>
    </>
  );
};

export default AgentsListRoute;
