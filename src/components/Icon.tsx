import React from 'react';
import type { LucideIcon } from 'lucide-react';

/** One icon style for the whole console: lucide, 14px, 2px stroke. */
export const ICON_SIZE = 14;
export const ICON_STROKE = 2;

/**
 * An icon from lucide-react. Decorative icons are hidden from assistive tech. An icon-only control passes `label`,
 * which becomes its accessible name; the control also needs a tooltip (`title`).
 */
export const Icon: React.FC<{ icon: LucideIcon; label?: string; className?: string; size?: number }> = ({
  icon: I,
  label,
  className = '',
  size = ICON_SIZE
}) => (
  <I
    size={size}
    strokeWidth={ICON_STROKE}
    className={`shrink-0 ${className}`}
    aria-hidden={label ? undefined : true}
    role={label ? 'img' : undefined}
    aria-label={label}
    focusable="false"
  />
);
