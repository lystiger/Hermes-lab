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
  window: string;
  unknownReason: string;
  tone?: string;
  note?: string;
}> = ({ label, value, limit, unit = '', window, unknownReason, tone = '#8C949F', note }) => {
  const known = typeof value === 'number';
  const hasLimit = typeof limit === 'number' && limit > 0;
  const pct = known && hasLimit ? Math.max(0, Math.min(100, (value / limit) * 100)) : null;

  return (
    <div className="flex flex-col gap-1.5 min-w-0">
      <div className="flex items-baseline justify-between gap-2 font-mono-code text-[11px]">
        <span className="text-[#8C949F] tracking-wider">{label}</span>
        <span className="text-[#E6E9ED]">
          {known ? (
            <>
              {value.toLocaleString()}
              {unit ? ` ${unit}` : ''}
              {hasLimit ? <span className="text-[#5C646E]"> / {limit!.toLocaleString()}</span> : null}
            </>
          ) : (
            <UnknownValue reason={unknownReason} />
          )}
        </span>
      </div>
      {pct !== null ? (
        <div role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)} className="h-2 bg-[#14171C] relative">
          <div className="absolute left-0 top-0 bottom-0" style={{ width: `${pct}%`, backgroundColor: tone }} />
        </div>
      ) : (
        <div className="h-2 bg-[#14171C] border border-dashed border-[#1F242B]" aria-hidden="true" />
      )}
      <div className="flex flex-wrap justify-between gap-2 font-mono-code text-[10px] text-[#5C646E]">
        <span>{window}</span>
        {note && <span>{note}</span>}
      </div>
    </div>
  );
};

/** Meters for one provider. Each carries its window label; limits appear only when the provider reported them. */
export const ProviderMeters: React.FC<{ provider: ProviderTelemetry }> = ({ provider }) => {
  const usage = provider.usage;
  const src = sourceLabel(usage?.source);
  const successes = provider.successCount;
  return (
    <section aria-label={`Meters for ${provider.providerId}`} className="p-4 bg-[#101216] border border-[#1F242B] flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2 font-mono-code text-[11px]">
        <span className="text-[13px] text-[#E6E9ED] font-semibold">{provider.providerId}</span>
        <span className="text-[#8C949F]">status {provider.status}</span>
        <span style={{ color: src.color }}>{src.text}</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <Meter
          label="SUCCESS RATE"
          value={provider.successRate === null ? undefined : Math.round(provider.successRate * 100)}
          limit={100}
          unit="%"
          window={PROCESS_WINDOW}
          unknownReason="No requests have been made, so no success rate exists"
          tone="#3FB950"
          note={`${successes} ok · ${provider.failureCount} failed`}
        />
        <Meter
          label="REQUESTS LEFT"
          value={usage?.requestsRemaining}
          limit={usage?.requestLimit}
          window={usage?.resetAt ? `resets ${usage.resetAt}` : 'provider window · reset not reported'}
          unknownReason="Provider did not report a remaining request count"
          tone="#7FB3D5"
        />
        <Meter
          label="TOKENS USED"
          value={usage?.tokensUsed}
          limit={usage?.tokenLimit}
          unit="tok"
          window={PROCESS_WINDOW}
          unknownReason="Provider did not report token usage"
          tone="#CBA35C"
        />
        <Meter
          label="CONTEXT"
          value={usage?.contextUsed}
          limit={usage?.contextWindow}
          unit="tok"
          window="current context window"
          unknownReason="Provider did not report context use"
          tone="#A5D6FF"
        />
      </div>
      {provider.throttlingCount > 0 && (
        <div className="font-mono-code text-[11px] text-[#E3A008]">
          {provider.throttlingCount} throttling event(s) · {PROCESS_WINDOW}
        </div>
      )}
    </section>
  );
};
