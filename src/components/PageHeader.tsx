import React from 'react';
import { Freshness } from './DataStates';

export interface HeaderCount {
  label: string;
  value: React.ReactNode;
  /** Small, dim unit shown after the big number (e.g. "tok", "%"). */
  unit?: string;
  tone?: string;
  title?: string;
}

/** Page header (research §2.2): display-font title, subtitle, and live counts with small dim units. */
export const PageHeader: React.FC<{
  title: string;
  subtitle?: React.ReactNode;
  counts?: HeaderCount[];
  actions?: React.ReactNode;
  /** When the page's data was last updated from Hermes (epoch ms). Shown as "updated HH:MM:SS". */
  updatedAt?: number | null;
}> = ({ title, subtitle, counts = [], actions, updatedAt }) => (
  <header className="sticky top-0 z-20 px-6 pt-6 pb-5 border-b border-lys-subtle bg-lys-surface-0 flex flex-col gap-4">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="font-display text-[30px] leading-none font-semibold text-lys-primary break-words">{title}</h1>
        {subtitle && <p className="mt-2 text-[13px] text-lys-muted break-words">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {updatedAt !== undefined && <Freshness at={updatedAt} />}
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
    </div>
    {counts.length > 0 && (
      <dl className="flex flex-wrap gap-x-10 gap-y-3">
        {counts.map((c) => (
          <div key={c.label} className="flex flex-col gap-1 min-w-[90px]" title={c.title}>
            <dt className="text-[11px] tracking-wider uppercase text-lys-faint">{c.label}</dt>
            <dd className="flex items-baseline gap-1.5">
              <span className="font-display text-[28px] leading-none font-semibold lys-metric" style={{ color: c.tone ?? 'var(--lys-text-primary)' }}>
                {c.value}
              </span>
              {c.unit && <span className="text-[12px] text-lys-faint">{c.unit}</span>}
            </dd>
          </div>
        ))}
      </dl>
    )}
  </header>
);
