import React from 'react';

export interface PillOption {
  id: string;
  label: string;
  count?: number;
  /** Optional colour for the count, e.g. red for Failed. */
  tone?: string;
}

/** Horizontal filter strip with live counts. Used on Queue, Events and Agents. */
export const FilterPills: React.FC<{
  label: string;
  options: PillOption[];
  value: string;
  onChange: (id: string) => void;
}> = ({ label, options, value, onChange }) => (
  <div role="group" aria-label={label} className="flex flex-wrap gap-1.5 font-mono-code text-[11px]">
    {options.map((o) => {
      const active = o.id === value;
      return (
        <button
          key={o.id}
          type="button"
          aria-pressed={active}
          onClick={() => onChange(o.id)}
          className={`px-2.5 py-1 border cursor-pointer transition-colors ${
            active ? 'text-lys-primary bg-lys-surface-interactive border-lys-strong' : 'text-lys-muted border-lys-subtle hover:border-lys-strong'
          }`}
        >
          {o.label}
          {o.count !== undefined && (
            <span className="ml-1.5" style={{ color: o.tone ?? 'var(--lys-text-faint)' }}>
              {o.count}
            </span>
          )}
        </button>
      );
    })}
  </div>
);
