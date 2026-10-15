import React from 'react';
import { AgentSummary } from '../../api/types';
import { agentAccent } from '../../theme/agents';
import { agentArt } from '../../theme/agentArt';
import { FocalImage } from '../../components/FocalImage';
import { UNKNOWN } from '../../components/DataStates';

/** Accent for an agent in the UI: its variable first, then any backend colour, then neutral. */
export function presenceAccent(agent: { id: string; presentation?: { accentColor?: string } }): string {
  return agentAccent(agent.id) || agent.presentation?.accentColor || 'var(--lys-text-muted)';
}

/** Compact agent identity: square focal portrait, name, status and the current task Hermes reports. */
export const AgentPresence: React.FC<{ agent: AgentSummary; selected?: boolean; onClick?: () => void; index?: number }> = ({
  agent,
  selected = false,
  onClick,
  index = 0
}) => {
  const accent = presenceAccent(agent);
  const art = agentArt(agent.id);
  const running = agent.status === 'RUNNING';
  const body = (
    <>
      <div className="flex gap-3 items-center min-w-0">
        {art ? (
          <FocalImage src={art.avatar} alt={`${agent.displayName} portrait`} focus={art.avatarFocus} className="h-14 w-14 shrink-0 border border-lys-default" />
        ) : (
          <div className="h-14 w-14 shrink-0 bg-lys-surface-2 border border-lys-default" aria-hidden="true" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[15px] font-semibold text-lys-primary break-words min-w-0">{agent.displayName}</span>
            <span className={`text-[10px] tracking-wider uppercase ${running ? 'text-lys-success' : 'text-lys-muted'}`}>{agent.status}</span>
          </div>
          <div className="mt-0.5 text-[12px] text-lys-muted break-words">{agent.role || UNKNOWN}</div>
          <div className="mt-0.5 text-[12px] text-lys-faint break-words">{agent.currentTask || 'no current task reported'}</div>
        </div>
      </div>
    </>
  );
  const style = { ['--lys-stagger' as string]: index, borderLeft: `3px solid ${accent}` } as React.CSSProperties;
  if (!onClick) {
    return <div className="lys-enter p-4 bg-lys-surface-1" style={style}>{body}</div>;
  }
  return (
    <button
      type="button"
      data-nav-item
      role="option"
      aria-selected={selected}
      onClick={onClick}
      className={`lys-enter w-full text-left p-3 cursor-pointer transition-colors ${selected ? 'bg-lys-surface-2' : 'bg-lys-surface-1 hover:bg-lys-surface-2'}`}
      style={style}
    >
      {body}
    </button>
  );
};
