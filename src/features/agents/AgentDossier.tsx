import React, { useState } from 'react';
import { PanelRightClose, PanelRightOpen } from 'lucide-react';
import { Icon } from '../../components/Icon';
import { AgentDetail } from '../../api/types';
import { Freshness, UnknownValue } from '../../components/DataStates';
import { CopyId } from '../../components/CopyId';
import { Card } from '../../components/Card';
import { FocalImage } from '../../components/FocalImage';
import { HeaderNotReported, NotReportedItem } from '../../components/NotReported';
import { agentArt } from '../../theme/agentArt';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { AgentContextMeter } from './AgentContextMeter';
import { presenceAccent } from './AgentPresence';
import { AgentModelSelector } from './AgentModelSelector';

const Spec: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex flex-col gap-1 min-w-0">
    <span className="text-[10px] font-medium tracking-wider uppercase text-lys-faint">{label}</span>
    <span className="text-[14px] text-lys-primary truncate" title={typeof children === 'string' ? children : undefined}>
      {children}
    </span>
  </div>
);

const NOT_REPORTED: NotReportedItem[] = [
  { label: 'run history', reason: 'Hermes exposes no per-agent run list in this console yet' },
  { label: 'activity feed', reason: 'Hermes does not report a live activity feed per agent' },
  { label: 'provider quota', reason: 'Hermes reports no provider quota for this agent' },
  { label: 'permission matrix', reason: 'Hermes does not expose tool or permission grants' }
];

/**
 * Agent dossier: portrait at sensible fixed size (~1/3 width capped), information panel getting the rest.
 */
export const AgentDossier: React.FC<{ agent: AgentDetail; updatedAt?: number | null }> = ({ agent, updatedAt }) => {
  const { setActiveDossierAgent } = useConsoleStore();
  const accent = presenceAccent(agent);
  const art = agentArt(agent.id);
  const isRunning = agent.status === 'RUNNING';
  // The portrait is the hero; the specs and model panels fold away so it can take the full width.
  const [detailsOpen, setDetailsOpen] = useState(true);

  return (
    <article aria-label={`Dossier for ${agent.displayName}`} className="flex flex-col min-w-0 min-h-full">
      <header className="px-6 pt-5 pb-4 border-b border-lys-subtle bg-lys-surface-0 flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0 flex items-center gap-3">
          <h2 className="font-display text-[26px] sm:text-[30px] leading-none font-semibold text-lys-primary">{agent.displayName}</h2>
          <span className={`text-[10px] font-mono-code uppercase px-1.5 py-0.5 border ${isRunning ? 'text-lys-success border-lys-success/40' : 'text-lys-muted border-lys-default'}`}>
            {agent.status}
          </span>
          <span className="text-lys-faint">·</span>
          <span className="text-[13px] text-lys-muted">{agent.model || UNKNOWN_LABEL}</span>
          <span className="text-lys-faint">·</span>
          <span className="text-[13px] text-lys-muted">{agent.provider || UNKNOWN_LABEL}</span>
          <span className="text-lys-faint">·</span>
          <CopyId value={agent.id} truncate className="text-lys-faint text-[11px]" />
        </div>
        <div className="flex items-center gap-3">
          <HeaderNotReported items={NOT_REPORTED} />
          <Freshness at={updatedAt} />
          <button
            type="button"
            disabled
            aria-label="Dispatch task"
            title="Operator commands are not available: the Hermes API has no command endpoint yet"
            className="text-[12px] px-3 py-1.5 border border-lys-default text-lys-faint cursor-not-allowed"
          >
            Dispatch
          </button>
          <button
            type="button"
            onClick={() => setDetailsOpen((open) => !open)}
            aria-expanded={detailsOpen}
            aria-controls="agent-details"
            aria-label={detailsOpen ? 'Hide details' : 'Show details'}
            title={detailsOpen ? 'Hide details' : 'Show details'}
            className="flex items-center gap-2 text-[12px] px-3 py-1.5 border border-lys-default text-lys-muted hover:bg-lys-surface-2 cursor-pointer transition-colors"
          >
            <Icon icon={detailsOpen ? PanelRightClose : PanelRightOpen} />
            Details
          </button>
          {art && (
            <button
              type="button"
              onClick={() => setActiveDossierAgent(agent)}
              className="text-[12px] px-3 py-1.5 border cursor-pointer hover:bg-lys-surface-2 transition-colors"
              style={{ borderColor: accent, color: accent }}
            >
              Character sheet
            </button>
          )}
        </div>
      </header>

      <div
        className={`flex-1 grid gap-5 p-6 items-stretch ${detailsOpen ? 'grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(280px,360px)] xl:grid-cols-[minmax(0,1fr)_340px]' : 'grid-cols-1'}`}
      >
        <Card accent={accent} label="Agent art" className="min-h-[460px] h-full w-full">
          {art ? (
            <FocalImage src={art.card} alt={`${agent.displayName} character art`} focus={art.cardFocus} className="absolute inset-0 h-full w-full" />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center text-[12px] text-lys-faint">No art</div>
          )}
        </Card>

        {detailsOpen && (
        <div id="agent-details" className="flex flex-col gap-5 min-w-0">
            <Card accent={accent} label="Specs">
              <div className="p-6 flex flex-col gap-6">
                <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-5">
                  <Spec label="Provider">{agent.provider || <UnknownValue reason="Hermes did not report a provider" />}</Spec>
                  <Spec label="Model">{agent.model || <UnknownValue reason="Hermes did not report a model" />}</Spec>
                  <Spec label="Role">{agent.role || <UnknownValue reason="Hermes did not report a role" />}</Spec>
                  <Spec label="Phase">{agent.phase || <UnknownValue reason="Hermes reports no phase for this agent" />}</Spec>
                  <Spec label="Current task">{agent.currentTask || <UnknownValue reason="Hermes reports no current task for this agent" />}</Spec>
                  <Spec label="Active tool">{agent.activeTool || <UnknownValue reason="Hermes reports no active tool for this agent" />}</Spec>
                </div>
                <div className="flex flex-col gap-2">
                  <span className="text-[10px] font-medium tracking-wider uppercase text-lys-faint">Capabilities</span>
                  {agent.capabilities.length === 0 ? (
                    <span className="text-[13px] text-lys-faint">none reported</span>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {agent.capabilities.map((cap) => (
                        <span key={cap} className="text-[12px] px-2 py-0.5 bg-lys-surface-2 text-lys-secondary rounded-sm">
                          {cap}
                        </span>
                      ))}
                    </div>
                )}
              </div>
              <AgentContextMeter agent={agent} />
            </div>
          </Card>

          <AgentModelSelector agentId={agent.id} accent={accent} />
        </div>
        )}
      </div>
    </article>
  );
};

const UNKNOWN_LABEL = '—';
