import React from 'react';
import { UnknownValue } from '../../components/DataStates';

/**
 * Run budget panel. Hermes exposes no sprint budget, cap or projection, so this shows that plainly
 * instead of drawing a meter with invented numbers.
 */
export const TokenBudgetMeter: React.FC = () => {
  return (
    <div className="p-5 border-r border-lys-subtle select-none bg-lys-base">
      <div className="text-[11px] tracking-wider text-lys-faint font-mono-code">
        2 · RUN BUDGET
      </div>
      <div className="mt-1 text-[11px] text-lys-faint">
        not reported by Hermes
      </div>

      <div className="mt-4 flex items-baseline gap-2 font-mono-code">
        <span className="text-[28px] text-lys-primary">
          <UnknownValue reason="Hermes exposes no sprint token budget" />
        </span>
      </div>

      <p className="mt-4 text-[12px] text-lys-muted leading-relaxed">
        No sprint cap, projection or hard-stop policy is available from the Hermes API, so no budget
        is shown. Measured token totals are wired with job telemetry in a later milestone.
      </p>
    </div>
  );
};
