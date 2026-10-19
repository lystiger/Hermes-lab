import React from 'react';

/**
 * The unified card for every panel: consistent border radius, surface-1 background,
 * hairline border, and an optional status/actor accent edge without gradient tints.
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
        <span aria-hidden="true" className="absolute left-0 top-0 bottom-0 w-[3px] z-10" style={{ background: accent }} />
      )}
      <div className={`relative h-full ${bodyClassName}`}>{children}</div>
    </div>
  </Tag>
);
