import React from 'react';
import { Freshness } from './DataStates';
import { HeaderNotReported, NotReportedItem } from './NotReported';

export interface HeaderCount {
  label: string;
  value: React.ReactNode;
  /** Small, dim unit shown after the big number (e.g. "tok", "%"). */
  unit?: string;
  tone?: string;
  title?: string;
}

/** Unified page header: title row with right-aligned freshness/actions, and an equal-column stat strip. */
export const PageHeader: React.FC<{
  title: string;
  subtitle?: React.ReactNode;
  counts?: HeaderCount[];
  actions?: React.ReactNode;
  notReported?: NotReportedItem[];
  /** When the page's data was last updated from Hermes (epoch ms). Shown as "updated HH:MM:SS". */
  updatedAt?: number | null;
}> = ({ title, subtitle, counts, actions, notReported, updatedAt }) => (
  <header className="sticky top-0 z-20 px-6 pt-5 pb-4 border-b border-lys-subtle bg-lys-surface-0 flex flex-col gap-3">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div className="min-w-0 flex items-baseline gap-3">
        <h1 title={title} className="font-display text-[26px] sm:text-[28px] leading-none font-semibold text-lys-primary truncate">
          {title}
        </h1>
        {subtitle && <span className="text-[12px] text-lys-muted truncate">{subtitle}</span>}
      </div>
      <div className="flex items-center gap-3">
        {notReported && notReported.length > 0 && <HeaderNotReported items={notReported} />}
        {updatedAt !== undefined && <Freshness at={updatedAt} />}
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
    </div>
    {counts !== undefined && (
      <div className="pt-3 border-t border-lys-subtle/50 min-h-[58px]">
        {counts.length > 0 && (
          <dl className="grid grid-flow-col auto-cols-fr gap-4 items-end">
            {counts.map((c) => (
              <div key={c.label} className="flex flex-col gap-1 min-w-0" title={c.title}>
                <dt title={c.label} className="text-[11px] font-medium tracking-wider uppercase text-lys-faint truncate leading-normal">{c.label}</dt>
                <dd className="flex items-baseline gap-1.5 leading-none">
                  <span
                    className="font-display text-[26px] sm:text-[28px] leading-none font-semibold lys-metric"
                    style={{ color: c.tone ?? 'var(--lys-text-primary)' }}
                  >
                    {c.value}
                  </span>
                  {c.unit && (
                    <span className="text-[12px] text-lys-faint font-normal leading-none">{c.unit}</span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    )}
  </header>
);
