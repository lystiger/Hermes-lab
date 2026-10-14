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
  <div role="status" className="p-6 font-mono-code text-[12px] text-lys-muted">
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
    <div role="alert" className="m-4 p-4 border border-lys-danger/35 bg-lys-danger/5 font-mono-code text-[12px]">
      {unreachable ? (
        <>
          <div className="text-lys-danger">Can&apos;t reach Hermes</div>
          <div className="mt-1 text-lys-secondary break-words">
            {label} is not loading. Check that the Hermes runtime API is running at {(error as HermesUnreachableError).url}.
          </div>
        </>
      ) : (
        <>
          <div className="text-lys-danger">{label} failed</div>
          <div className="mt-1 text-lys-secondary break-words">{message}</div>
        </>
      )}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 px-2.5 py-1 border border-lys-default text-lys-primary hover:border-lys-strong bg-lys-surface-1 cursor-pointer transition-colors"
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
    <div role="alert" className="mb-2 px-3 py-2 border border-lys-warning/35 bg-lys-warning/6 font-mono-code text-[11px] text-lys-warning">
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
  <div className="p-6 text-center font-mono-code text-[12px] text-lys-faint">{children}</div>
);

/** When a view's data was last fetched from Hermes. `at` is epoch milliseconds. */
export const Freshness: React.FC<{ at: number | null | undefined }> = ({ at }) => (
  <span className="font-mono-code text-[11px] text-lys-faint">
    {at ? `updated ${formatTimeOfDay(at)}` : 'not loaded yet'}
  </span>
);

/**
 * One rule for a loaded resource that may now be failing: with data the failure is a stale notice with retry;
 * without data it is the full error state. Callers render their own loading and empty states.
 */
export const ResourceError: React.FC<{ label: string; error: unknown; hasData: boolean; updatedAt?: number | null; onRetry?: () => void }> = ({
  label,
  error,
  hasData,
  updatedAt,
  onRetry
}) => {
  if (!error) return null;
  if (!hasData) return <ErrorState label={label} error={error} onRetry={onRetry} />;
  return (
    <div className="flex flex-col gap-1">
      <StaleNotice label={label} error={error} onRetry={onRetry} />
      {updatedAt !== undefined && (
        <span className="font-mono-code text-[10px] text-lys-faint">last loaded {updatedAt ? formatTimeOfDay(updatedAt) : 'never'}</span>
      )}
    </div>
  );
};
