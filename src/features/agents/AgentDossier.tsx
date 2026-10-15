import React from 'react';
import { AgentDetail } from '../../api/types';
import { Freshness, UnknownValue } from '../../components/DataStates';
import { CopyId } from '../../components/CopyId';
import { Card } from '../../components/Card';
import { FocalImage } from '../../components/FocalImage';
import { NotReported, NotReportedItem } from '../../components/NotReported';
import { agentArt } from '../../theme/agentArt';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { AgentContextMeter } from './AgentContextMeter';
import { presenceAccent } from './AgentPresence';

const Spec: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex flex-col gap-1 min-w-0">
    <span className="text-[10px] tracking-wider uppercase text-lys-faint">{label}</span>
    <span className="text-[14px] text-lys-primary break-words">{children}</span>
  </div>
);

const NOT_REPORTED: NotReportedItem[] = [
  { label: 'run history', reason: 'Hermes exposes no per-agent run list in this console yet' },
  { label: 'activity feed', reason: 'Hermes does not report a live activity feed per agent' },
  { label: 'provider quota', reason: 'Hermes reports no provider quota for this agent' },
  { label: 'permission matrix', reason: 'Hermes does not expose tool or permission grants' }
];

/**
 * Agent dossier (research §5.1, brief item 2): a large art pane on the left, cropped to the face with the agent's
 * accent edge, and the real specs on the right. Fields Hermes does not report stay unknown inside their panel.
 */
export const AgentDossier: React.FC<{ agent: AgentDetail; updatedAt?: number | null }> = ({ agent, updatedAt }) => {
  const { setActiveDossierAgent } = useConsoleStore();
  const accent = presenceAccent(agent);
  const art = agentArt(agent.id);
  const isRunning = agent.status === 'RUNNING';

  return (
    <article aria-label={`Dossier for ${agent.displayName}`} className="flex flex-col min-w-0 min-h-full">
      <header className="px-6 pt-6 pb-5 border-b border-lys-subtle bg-lys-surface-0 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="font-display text-[34px] leading-none font-semibold text-lys-primary">{agent.displayName}</h2>
            <span className={`text-[10px] tracking-wider uppercase border px-2 py-1 ${isRunning ? 'text-lys-success border-lys-success/40' : 'text-lys-muted border-lys-default'}`}>
              {agent.status}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-[13px] text-lys-muted">
            <span>{agent.model || UNKNOWN_LABEL}</span>
            <span className="text-lys-faint">·</span>
            <span>{agent.provider || UNKNOWN_LABEL}</span>
            <span className="text-lys-faint">·</span>
            <CopyId value={agent.id} className="text-lys-faint text-[11px]" />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Freshness at={updatedAt} />
          <button
            type="button"
            disabled
            title="Operator commands are not available: the Hermes API has no command endpoint yet"
            className="text-[12px] px-3 py-1.5 border border-lys-default text-lys-faint cursor-not-allowed"
          >
            dispatch task (unavailable)
          </button>
          {art && (
            <button
              type="button"
              onClick={() => setActiveDossierAgent(agent)}
              className="text-[12px] px-3 py-1.5 border cursor-pointer hover:bg-lys-surface-2"
              style={{ borderColor: accent, color: accent }}
            >
              view character sheet
            </button>
          )}
        </div>
      </header>

      <div className="flex-1 grid grid-cols-1 2xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-5 p-6 items-stretch">
        <Card accent={accent} label="Agent art" className="min-h-[560px]">
          {art ? (
            <FocalImage src={art.card} alt={`${agent.displayName} character art`} focus={art.cardFocus} className="absolute inset-0 h-full w-full" />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center text-[12px] text-lys-faint">no art for this agent</div>
          )}
        </Card>

        <div className="flex flex-col gap-5 min-w-0">
          <Card accent={accent} label="Specs">
            <div className="p-6 flex flex-col gap-6">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-5">
                <Spec label="Provider">{agent.provider || <UnknownValue reason="Not reported by Hermes" />}</Spec>
                <Spec label="Model">{agent.model || <UnknownValue reason="Not reported by Hermes" />}</Spec>
                <Spec label="Role">{agent.role || <UnknownValue reason="Not reported by Hermes" />}</Spec>
                <Spec label="Phase">{agent.phase || <UnknownValue reason="Hermes reports no phase for this agent" />}</Spec>
                <Spec label="Current task">{agent.currentTask || <UnknownValue reason="Hermes reports no current task for this agent" />}</Spec>
                <Spec label="Active tool">{agent.activeTool || <UnknownValue reason="Hermes reports no active tool for this agent" />}</Spec>
              </div>
              <div className="flex flex-col gap-2">
                <span className="text-[10px] tracking-wider uppercase text-lys-faint">Capabilities</span>
                {agent.capabilities.length === 0 ? (
                  <span className="text-[13px] text-lys-faint">none reported</span>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {agent.capabilities.map((cap) => (
                      <span key={cap} className="text-[12px] px-2 py-1 bg-lys-surface-2 text-lys-secondary">
                        {cap}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <AgentContextMeter agent={agent} />
            </div>
          </Card>

          <NotReported items={NOT_REPORTED} />
        </div>
      </div>
    </article>
  );
};

const UNKNOWN_LABEL = '—';
