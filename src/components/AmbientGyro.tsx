import React from 'react';

export const AmbientGyro: React.FC<{ size?: number; enabled?: boolean }> = ({ size = 150, enabled = true }) => {
  if (!enabled) return null;

  return (
    <div
      style={{ width: `${size}px`, height: `${size}px`, perspective: '520px' }}
      className="absolute right-6 top-2 opacity-50 pointer-events-none"
    >
      <div
        style={{
          transformStyle: 'preserve-3d',
          animation: 'lys-spin 26s linear infinite'
        }}
        className="absolute inset-0"
      >
        <div
          style={{ transform: 'translateZ(26px)' }}
          className="absolute left-[25px] top-[25px] w-[100px] height-[100px] h-[100px] border border-[rgba(91,140,255,0.5)]"
        />
        <div
          style={{ transform: 'translateZ(0px)' }}
          className="absolute left-[37px] top-[37px] w-[76px] h-[76px] border border-[rgba(217,160,91,0.45)]"
        />
        <div
          style={{ transform: 'translateZ(-26px)' }}
          className="absolute left-[49px] top-[49px] w-[52px] h-[52px] border border-[rgba(78,201,160,0.45)]"
        />
      </div>
      <div
        style={{
          transformStyle: 'preserve-3d',
          animation: 'lys-spin-rev 40s linear infinite'
        }}
        className="absolute inset-0"
      >
        <div
          style={{ transform: 'translateZ(10px)' }}
          className="absolute left-[44px] top-[44px] w-[62px] h-[62px] border border-dashed border-[rgba(203,163,92,0.35)]"
        />
      </div>
    </div>
  );
};
