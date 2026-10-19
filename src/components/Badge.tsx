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
  variant: _variant = 'status',
  color = 'var(--lys-text-muted)',
  dot = false,
  pulse: _pulse = false,
  className = ''
}) => {
  return (
    <span
      style={{
        color: color,
        borderColor: `color-mix(in srgb, ${color} 27%, transparent)`,
        backgroundColor: `color-mix(in srgb, ${color} 7%, transparent)`
      }}
      className={`inline-flex items-center gap-1.5 px-1.5 py-0.5 border font-sans text-[11px] uppercase tracking-wider ${className}`}
    >
      {dot && (
        <span
          style={{ backgroundColor: color }}
          className={`w-1.5 h-1.5 rounded-[1px]`}
        />
      )}
      {label}
    </span>
  );
};
