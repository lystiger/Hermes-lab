import React, { useState } from 'react';
import { Info } from 'lucide-react';

export interface NotReportedItem {
  label: string;
  /** Why Hermes does not provide it. Shown on hover. */
  reason: string;
}

/**
 * Info icon tooltip in the page header: lists values Hermes does not report without
 * taking page space with a persistent footer.
 */
export const HeaderNotReported: React.FC<{ items: NotReportedItem[] }> = ({ items }) => {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;

  return (
    <div className="relative inline-flex items-center">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        aria-label="Not reported by Hermes"
        className="p-1 text-lys-faint hover:text-lys-primary cursor-pointer transition-colors rounded"
        title="What Hermes does not report"
      >
        <Info size={15} aria-hidden="true" />
      </button>
      <div
        role="tooltip"
        className={`absolute right-0 top-full mt-1.5 z-50 w-72 p-3 bg-lys-surface-2 border border-lys-default rounded shadow-lg text-[11px] leading-relaxed transition-opacity ${
          open ? 'opacity-100 visible pointer-events-auto' : 'opacity-0 invisible pointer-events-none'
        }`}
      >
        <p className="text-lys-faint">
          <span className="text-lys-muted font-medium">Not reported by Hermes:</span>{' '}
          {items.map((item, i) => (
            <React.Fragment key={item.label}>
              {i > 0 && ' · '}
              <span title={item.reason} className="underline decoration-dotted underline-offset-2 cursor-help text-lys-secondary">
                {item.label}
              </span>
            </React.Fragment>
          ))}
        </p>
      </div>
    </div>
  );
};

/**
 * Default NotReported component. Renders as a header info tooltip or compact list.
 */
export const NotReported: React.FC<{ items: NotReportedItem[] }> = ({ items }) => {
  return <HeaderNotReported items={items} />;
};
