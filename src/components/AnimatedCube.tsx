import React from 'react';

export const AnimatedCube: React.FC<{ size?: number }> = ({ size = 26 }) => {
  const inner = Math.round(size * 0.54);
  const zTrans = Math.round(inner / 2);

  return (
    <div
      style={{ width: `${size}px`, height: `${size}px`, perspective: '220px' }}
      className="flex items-center justify-center pointer-events-none"
    >
      <div
        style={{
          width: `${inner}px`,
          height: `${inner}px`,
          transformStyle: 'preserve-3d',
          animation: 'lys-cube 9s linear infinite'
        }}
        className="relative"
      >
        <div
          style={{ transform: `translateZ(${zTrans}px)` }}
          className="absolute inset-0 border border-[#CBA35C]"
        />
        <div
          style={{ transform: `translateZ(-${zTrans}px)` }}
          className="absolute inset-0 border border-[rgba(203,163,92,0.45)]"
        />
        <div
          style={{ transform: 'rotateY(90deg)' }}
          className="absolute inset-0 border border-[rgba(203,163,92,0.3)]"
        />
        <div
          style={{ transform: 'rotateY(-90deg)' }}
          className="absolute inset-0 border border-[rgba(203,163,92,0.3)]"
        />
      </div>
    </div>
  );
};
