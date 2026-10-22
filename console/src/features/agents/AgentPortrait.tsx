import React from 'react';
import { AgentPresentation, AgentStatus } from '../../api/types';

interface AgentPortraitProps {
  displayName: string;
  presentation?: AgentPresentation;
  status?: AgentStatus;
  size?: 'sm' | 'md' | 'lg';
}

const SIZE_CLASSES = {
  sm: 'w-[52px] h-[52px] text-[22px]',
  md: 'w-[84px] h-[84px] text-[36px]',
  lg: 'w-[120px] h-[120px] text-[52px]'
} as const;

/** A framed square with the agent's initial in its accent colour. A running agent gets a brighter frame. */
export const AgentPortrait: React.FC<AgentPortraitProps> = ({ displayName, presentation, status = 'IDLE', size = 'md' }) => {
  const accentColor = presentation?.accentColor || 'var(--lys-text-muted)';
  const initial = displayName ? displayName.charAt(0).toUpperCase() : '?';
  const isRunning = status === 'RUNNING';

  return (
    <div
      aria-hidden="true"
      style={{
        color: accentColor,
        borderColor: isRunning ? accentColor : 'var(--lys-border-subtle)',
        backgroundColor: 'var(--lys-surface-0)'
      }}
      className={`flex-shrink-0 border flex items-center justify-center font-display font-semibold select-none ${SIZE_CLASSES[size]}`}
    >
      {initial}
    </div>
  );
};
