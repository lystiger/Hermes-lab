import React from 'react';
import { UNKNOWN } from '../api/unknown';
import { HermesUnreachableError } from '../api/connection';
import { formatTimeOfDay } from '../features/time/format';

export { UNKNOWN };

/** True when a value came from the API (not missing and not the unknown placeholder). */
export function isKnown(value: unknown): boolean {
  return value !== undefined && value !== null && value !== '' && value !== UNKNOWN;
}

/** An unknown value with the reason shown on hover and to assistive tech. */
export const UnknownValue: React.FC<{ reason: string; className?: string }> = ({ reason, className }) => (
  <span title={reason} aria-label={`unknown: ${reason}`} className={className}>
    {UNKNOWN}
  </span>
);

export const LoadingState: React.FC<{ label: string }> = ({ label }) => (
  <div role="status" className="p-6 font-mono-code text-[12px] text-[#8C949F]">
    {label}
  </div>
);

export const ErrorState: React.FC<{ label: string; error: unknown; onRetry?: () => void }> = ({
  label,
  error,
  onRetry
}) => {
  const message = error instanceof Error ? error.message : String(error);
  const unreachable = error instanceof HermesUnreachableError;
  return (
    <div role="alert" className="m-4 p-4 border border-[rgba(242,85,90,0.35)] bg-[rgba(242,85,90,0.05)] font-mono-code text-[12px]">
      {unreachable ? (
        <>
          <div className="text-[#F2555A]">Can&apos;t reach Hermes</div>
          <div className="mt-1 text-[#B7BEC7] break-words">
            {label} is not loading. Check that the Hermes runtime API is running at {(error as HermesUnreachableError).url}.
          </div>
        </>
      ) : (
        <>
          <div className="text-[#F2555A]">{label} failed</div>
          <div className="mt-1 text-[#B7BEC7] break-words">{message}</div>
        </>
      )}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 px-2.5 py-1 border border-[#2A3038] text-[#E6E9ED] hover:border-[#5C646E] bg-[#101216] cursor-pointer transition-colors"
        >
          retry
        </button>
      )}
    </div>
  );
};

/** A refresh failed after data had loaded: the list below is the last good copy and says so. */
export const StaleNotice: React.FC<{ label: string; error: unknown; onRetry?: () => void }> = ({
  label,
  error,
  onRetry
}) => {
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="mb-2 px-3 py-2 border border-[rgba(227,160,8,0.35)] bg-[rgba(227,160,8,0.06)] font-mono-code text-[11px] text-[#E3A008]">
      {label} refresh failed, showing last loaded data: {message}
      {onRetry && (
        <button type="button" onClick={onRetry} className="ml-3 underline cursor-pointer">
          retry
        </button>
      )}
    </div>
  );
};

export const EmptyState: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="p-6 text-center font-mono-code text-[12px] text-[#5C646E]">{children}</div>
);

/** When a view's data was last fetched from Hermes. `at` is epoch milliseconds. */
export const Freshness: React.FC<{ at: number | null | undefined }> = ({ at }) => (
  <span className="font-mono-code text-[11px] text-[#5C646E]">
    {at ? `updated ${formatTimeOfDay(at)}` : 'not loaded yet'}
  </span>
);
