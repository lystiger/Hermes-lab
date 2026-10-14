import React from 'react';

export interface NotReportedItem {
  label: string;
  /** Why Hermes does not provide it. Shown on hover. */
  reason: string;
}

/**
 * One compact line for values Hermes does not report (research brief: noise rule). Panels whose content is only
 * unknown are not rendered; they are listed here instead.
 */
export const NotReported: React.FC<{ items: NotReportedItem[] }> = ({ items }) => {
  if (items.length === 0) return null;
  return (
    <p className="text-[12px] text-lys-faint">
      <span className="text-lys-muted">Not reported by Hermes:</span>{' '}
      {items.map((item, i) => (
        <React.Fragment key={item.label}>
          {i > 0 && ' · '}
          <span title={item.reason} className="underline decoration-dotted underline-offset-2 cursor-help">
            {item.label}
          </span>
        </React.Fragment>
      ))}
    </p>
  );
};
