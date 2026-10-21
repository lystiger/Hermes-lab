import React, { useState, useEffect, useId } from 'react';
import { hermesApi, isMockMode } from '../../api/client';
import { useAgentModels } from '../../api/hooks';
import { Card } from '../../components/Card';
import { LoadingState, ErrorState, EmptyState, Freshness, StaleNotice } from '../../components/DataStates';

export function getValidEffortOptions(agentId: string): (string | null)[] {
  const id = agentId.toLowerCase();
  if (id === 'claude') {
    return [null, 'low', 'medium', 'high', 'xhigh', 'max'];
  }
  if (id === 'gemini' || id === 'agy') {
    return [null, 'low', 'medium', 'high'];
  }
  if (id === 'codex') {
    return [null, 'minimal', 'low', 'medium', 'high', 'xhigh'];
  }
  return [null];
}

interface AgentModelSelectorProps {
  agentId: string;
  accent?: string;
}

export const AgentModelSelector: React.FC<AgentModelSelectorProps> = ({ agentId, accent }) => {
  const { models, loading, error, updatedAt, stale, refetch } = useAgentModels();
  const agentKey = agentId.toLowerCase();
  const config = models ? models[agentKey] : null;

  // Track explicit user selection; null/undefined means fallback to baseline server config
  const [userModel, setUserModel] = useState<string | null>(null);
  const [userEffort, setUserEffort] = useState<string | null | undefined>(undefined);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<unknown | null>(null);

  const modelSelectId = useId();
  const effortSelectId = useId();

  // Reset user selection when switching agent
  useEffect(() => {
    setUserModel(null);
    setUserEffort(undefined);
    setSaveError(null);
  }, [agentId]);

  // 1. Loading state (no data yet)
  if (loading && !models) {
    return (
      <Card accent={accent} label="Model configuration">
        <LoadingState label="Agent models" />
      </Card>
    );
  }

  // 2. Error state (initial fetch failed)
  if (error && !models) {
    return (
      <Card accent={accent} label="Model configuration">
        <ErrorState label="Agent models" error={error} onRetry={refetch} />
      </Card>
    );
  }

  // 3. Empty state (no model config or empty allowed list, <= 5 words)
  if (!config || !Array.isArray(config.allowed) || config.allowed.length === 0) {
    return (
      <Card accent={accent} label="Model configuration">
        <div className="p-6">
          <EmptyState>No models</EmptyState>
        </div>
      </Card>
    );
  }

  // 4. Data state
  const effortOptions = getValidEffortOptions(agentId);

  const baselineModel = config.configured?.default ?? '';
  const baselineEffort = config.configured?.effort ?? null;

  const currentModel = userModel !== null ? userModel : baselineModel;
  const currentEffort = userEffort !== undefined ? userEffort : baselineEffort;

  const hasChanged = currentModel !== baselineModel || currentEffort !== baselineEffort;
  const isValid = currentModel !== '' && config.allowed.includes(currentModel);
  const canSave = !isMockMode && !isSaving && hasChanged && isValid;

  const isNothingConfigured = !config.configured || config.configured.default === null;

  const handleSave = async () => {
    if (!canSave) return;
    setIsSaving(true);
    setSaveError(null);
    try {
      await hermesApi.setAgentModel(agentId, currentModel, currentEffort);
      await refetch();
      setUserModel(null);
      setUserEffort(undefined);
    } catch (err) {
      setSaveError(err);
    } finally {
      setIsSaving(false);
    }
  };

  const mockTooltip = isMockMode ? 'Model configuration is disabled in mock mode' : undefined;

  return (
    <Card accent={accent} label="Model configuration">
      <div className="p-6 flex flex-col gap-5">
        {stale && <StaleNotice label="Agent models" error={error} onRetry={refetch} />}

        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-lys-subtle pb-3">
          <span className="text-[10px] font-medium tracking-wider uppercase text-lys-faint">
            Model configuration
          </span>
          <Freshness at={updatedAt} />
        </div>

        {/* Compact block: Configured vs Last used */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Configured Block */}
          <div
            aria-label="Configured model"
            className="p-3.5 rounded-sm bg-lys-surface-0 border border-lys-default flex flex-col gap-2"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-semibold tracking-wider uppercase text-lys-secondary">
                Configured
              </span>
              {isNothingConfigured && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-sm bg-lys-surface-2 text-lys-muted font-mono-code uppercase">
                  CLI default
                </span>
              )}
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-[10px] uppercase text-lys-faint">Model</span>
              <span
                className="text-[13px] font-mono-code font-medium text-lys-primary truncate"
                title={config.configured?.default ?? 'CLI default'}
              >
                {config.configured?.default ?? '—'}
              </span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-[10px] uppercase text-lys-faint">Effort</span>
              <span className="text-[12px] text-lys-secondary">
                {config.configured?.effort ?? '—'}
              </span>
            </div>
          </div>

          {/* Last Used Block */}
          <div
            aria-label="Last used model"
            className="p-3.5 rounded-sm bg-lys-surface-0 border border-dashed border-lys-subtle flex flex-col gap-2"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-semibold tracking-wider uppercase text-lys-faint">
                Last used
              </span>
              {Boolean(config.lastUsed?.source) && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-sm bg-lys-surface-2 text-lys-muted font-mono-code uppercase">
                  {config.lastUsed?.source}
                </span>
              )}
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-[10px] uppercase text-lys-faint">Model</span>
              <span
                className="text-[13px] font-mono-code text-lys-muted truncate"
                title={config.lastUsed?.model ?? '—'}
              >
                {config.lastUsed?.model ?? '—'}
              </span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-[10px] uppercase text-lys-faint">Effort</span>
              <span className="text-[12px] text-lys-muted">
                {config.lastUsed?.effort ?? '—'}
              </span>
            </div>
          </div>
        </div>

        {/* Save error state (standard ErrorState with retry and message preserved) */}
        {saveError ? (
          <ErrorState label="Model update" error={saveError} onRetry={handleSave} />
        ) : null}

        {/* Form Controls: Model & Effort selectors */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor={modelSelectId} className="text-[10px] font-medium tracking-wider uppercase text-lys-faint">
              Model
            </label>
            <select
              id={modelSelectId}
              aria-label="Model"
              value={currentModel}
              onChange={(e) => {
                setUserModel(e.target.value);
                setSaveError(null);
              }}
              disabled={isMockMode || isSaving}
              title={mockTooltip}
              className="px-2.5 py-1.5 bg-lys-surface-0 border border-lys-default text-lys-primary font-mono-code text-[12px] rounded-sm focus:outline-none focus:border-lys-strong focus:ring-1 focus:ring-lys-strong disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {!config.allowed.includes(currentModel) && (
                <option value="" disabled hidden>
                  —
                </option>
              )}
              {config.allowed.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor={effortSelectId} className="text-[10px] font-medium tracking-wider uppercase text-lys-faint">
              Effort
            </label>
            <select
              id={effortSelectId}
              aria-label="Effort"
              value={currentEffort ?? ''}
              onChange={(e) => {
                setUserEffort(e.target.value === '' ? null : e.target.value);
                setSaveError(null);
              }}
              disabled={isMockMode || isSaving || effortOptions.length <= 1}
              title={mockTooltip || (effortOptions.length <= 1 ? 'Effort not configurable for this agent' : undefined)}
              className="px-2.5 py-1.5 bg-lys-surface-0 border border-lys-default text-lys-primary font-mono-code text-[12px] rounded-sm focus:outline-none focus:border-lys-strong focus:ring-1 focus:ring-lys-strong disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {effortOptions.map((eff) => (
                <option key={eff ?? 'null'} value={eff ?? ''}>
                  {eff ?? '—'}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Footer: note and Save button */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
          <span className="text-[11px] text-lys-faint" title="Applies to the next phase">
            Applies to the next phase
          </span>
          <button
            type="button"
            onClick={handleSave}
            disabled={!canSave}
            title={mockTooltip}
            className={`text-[12px] px-3.5 py-1.5 font-medium border rounded-sm transition-colors ${
              canSave
                ? 'bg-lys-surface-2 border-lys-strong text-lys-primary hover:bg-lys-surface-3 cursor-pointer'
                : 'bg-lys-surface-1 border-lys-default text-lys-faint cursor-not-allowed opacity-50'
            }`}
          >
            {isSaving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </Card>
  );
};
