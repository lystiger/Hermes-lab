import React from 'react';

/**
 * The one card for every panel (research §2.3, §6): chamfered corners, the raised surface-1 layer on a
 * surface-0 page, a hairline border, and an optional accent edge in an agent or status colour.
 */
export const Card: React.FC<{
  accent?: string;
  className?: string;
  bodyClassName?: string;
  children: React.ReactNode;
  as?: 'div' | 'section' | 'article';
  label?: string;
}> = ({ accent, className = '', bodyClassName = '', children, as: Tag = 'div', label }) => (
  <Tag aria-label={label} className={`lys-card-outer relative p-px bg-lys-subtle ${className}`}>
    <div className="lys-card-inner relative h-full bg-lys-surface-1">
      {accent && (
        <>
          <span aria-hidden="true" className="absolute left-0 top-0 bottom-0 w-[3px] z-10" style={{ background: accent }} />
          <span
            aria-hidden="true"
            className="absolute inset-0 pointer-events-none"
            style={{ background: `linear-gradient(90deg, color-mix(in srgb, ${accent} 12%, transparent), transparent 45%)` }}
          />
        </>
      )}
      <div className={`relative h-full ${bodyClassName}`}>{children}</div>
    </div>
  </Tag>
);
