import React from 'react';
import { ProviderTelemetry } from '../../api/types';
import { CAPACITY_WINDOW_LABEL } from '../../api/mapping';
import { UnknownValue } from '../../components/DataStates';
import { sourceLabel } from './ProviderTelemetryList';

export const PROCESS_WINDOW = CAPACITY_WINDOW_LABEL;

/**
 * A meter with its window label. The bar is drawn only when both the value and its limit are reported;
 * otherwise the value stands alone, or shows as unknown with the reason on hover.
 */
export const Meter: React.FC<{
  label: string;
  value: number | null | undefined;
  limit?: number | null;
  unit?: string;
  window?: string;
  unknownReason: string;
  tone?: string;
  note?: string;
}> = ({ label, value, limit, unit = '', window, unknownReason, tone = 'var(--lys-text-muted)', note }) => {
  const known = typeof value === 'number';
  const hasLimit = typeof limit === 'number' && limit > 0;
  const pct = known && hasLimit ? Math.max(0, Math.min(100, (value / limit) * 100)) : null;

  const showWindow = window && window !== PROCESS_WINDOW;

  return (
    <div className="flex flex-col gap-1.5 min-w-0">
      <div className="lys-metric flex items-baseline justify-between gap-2 font-sans text-[11px]">
        <span className="text-lys-muted font-medium tracking-wider uppercase">{label}</span>
        <span className="text-lys-primary">
          {known ? (
            <>
              {value.toLocaleString()}
              {unit ? ` ${unit}` : ''}
              {hasLimit ? <span className="text-lys-faint"> / {limit!.toLocaleString()}</span> : null}
            </>
          ) : (
            <UnknownValue reason={unknownReason} />
          )}
        </span>
      </div>
      {pct !== null ? (
        <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)} className="h-2 bg-lys-surface-2 relative rounded-full overflow-hidden">
          <div className="absolute left-0 top-0 bottom-0" style={{ width: `${pct}%`, backgroundColor: tone }} />
        </div>
      ) : (
        <div className="h-2 bg-lys-surface-2 border border-dashed border-lys-subtle rounded-full" aria-hidden="true" />
      )}
      {(showWindow || note) && (
        <div className="flex flex-wrap justify-between gap-2 font-sans text-[10px] text-lys-faint">
          {showWindow ? <span>{window}</span> : <span />}
          {note && <span>{note}</span>}
        </div>
      )}
    </div>
  );
};

/** Meters for one provider. Four standard fields in consistent positions without repeated qualifiers. */
export const ProviderMeters: React.FC<{ provider: ProviderTelemetry }> = ({ provider }) => {
  const usage = provider.usage;
  const src = sourceLabel(usage?.source);
  const successes = provider.successCount;
  return (
    <section aria-label={`Meters for ${provider.providerId}`} className="p-5 flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2 font-sans text-[11px]">
        <span className="text-[14px] text-lys-primary font-semibold">{provider.providerId}</span>
        <div className="flex items-center gap-2">
          <span className="text-lys-muted uppercase font-mono-code text-[10px]">{provider.status}</span>
          <span style={{ color: src.color }}>{src.text}</span>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Meter
          label="SUCCESS RATE"
          value={provider.successRate === null ? undefined : Math.round(provider.successRate * 100)}
          limit={100}
          unit="%"
          unknownReason="No requests have been made, so no success rate exists"
          tone="var(--lys-status-success)"
          note={`${successes} ok · ${provider.failureCount} failed`}
        />
        <Meter
          label="REQUESTS LEFT"
          value={usage?.requestsRemaining}
          limit={usage?.requestLimit}
          window={usage?.resetAt ? `resets ${usage.resetAt}` : undefined}
          unknownReason="Provider did not report a remaining request count"
          tone="var(--lys-accent-sky)"
        />
        <Meter
          label="TOKENS USED"
          value={usage?.tokensUsed}
          limit={usage?.tokenLimit}
          unit="tok"
          unknownReason="Provider did not report token usage"
          tone="var(--lys-accent-gold)"
        />
        <Meter
          label="CONTEXT"
          value={usage?.contextUsed}
          limit={usage?.contextWindow}
          unit="tok"
          unknownReason="Provider did not report context use"
          tone="var(--lys-text-secondary)"
        />
      </div>
      {provider.throttlingCount > 0 && (
        <div className="font-sans text-[11px] text-lys-warning">
          {provider.throttlingCount} throttling events
        </div>
      )}
    </section>
  );
};
