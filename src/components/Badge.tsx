import React from 'react';

interface BadgeProps {
  label: string;
  variant?: 'status' | 'prio' | 'phase' | 'model';
  color?: string;
  dot?: boolean;
  pulse?: boolean;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  label,
  variant = 'status',
  color = '#8C949F',
  dot = false,
  pulse = false,
  className = ''
}) => {
  return (
    <span
      style={{
        color: color,
        borderColor: `${color}44`,
        backgroundColor: `${color}11`
      }}
      className={`inline-flex items-center gap-1.5 px-1.5 py-0.5 border font-mono-code text-[11px] uppercase tracking-wider ${className}`}
    >
      {dot && (
        <span
          style={{ backgroundColor: color }}
          className={`w-1.5 h-1.5 rounded-[1px] ${pulse ? 'animate-pulse' : ''}`}
        />
      )}
      {label}
    </span>
  );
};
