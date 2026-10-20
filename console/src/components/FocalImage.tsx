import React from 'react';
import type { Focus } from '../theme/agentArt';

/**
 * An image cropped around a focal point: it fills its box (object-fit cover) and is scaled about the focus,
 * so the face stays in view and the rest of the sheet falls outside the box.
 */
export const FocalImage: React.FC<{ src: string; alt: string; focus: Focus; className?: string }> = ({ src, alt, focus, className = '' }) => (
  <div className={`relative overflow-hidden ${className}`}>
    <img
      src={src}
      alt={alt}
      draggable={false}
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        objectFit: 'cover',
        objectPosition: `${focus.x * 100}% ${focus.y * 100}%`,
        transform: `scale(${focus.zoom})`,
        transformOrigin: `${focus.x * 100}% ${focus.y * 100}%`
      }}
    />
  </div>
);
