import React from 'react';

// Still at rest; it turns while the sidebar brand is hovered (no continuous idle animation).

export const AnimatedCube: React.FC<{ size?: number }> = ({ size = 26 }) => {
  const inner = Math.round(size * 0.54);
  const zTrans = Math.round(inner / 2);

  return (
    <div
      style={{ width: `${size}px`, height: `${size}px`, perspective: '220px' }}
      className="group flex items-center justify-center pointer-events-none"
    >
      <div
        style={{
          width: `${inner}px`,
          height: `${inner}px`,
          transformStyle: 'preserve-3d'
        }}
        className="relative group-hover:animate-[lys-cube_9s_linear_infinite]"
      >
        <div
          style={{ transform: `translateZ(${zTrans}px)` }}
          className="absolute inset-0 border border-lys-gold"
        />
        <div
          style={{ transform: `translateZ(-${zTrans}px)` }}
          className="absolute inset-0 border border-lys-gold/45"
        />
        <div
          style={{ transform: 'rotateY(90deg)' }}
          className="absolute inset-0 border border-lys-gold/30"
        />
        <div
          style={{ transform: 'rotateY(-90deg)' }}
          className="absolute inset-0 border border-lys-gold/30"
        />
      </div>
    </div>
  );
};
