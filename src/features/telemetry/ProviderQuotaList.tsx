import React from 'react';
import { useTelemetry } from '../../api/hooks';

export const ProviderQuotaList: React.FC<{ compact?: boolean }> = ({ compact = false }) => {
  const { quotas } = useTelemetry();

  if (compact) {
    return (
      <div className="p-3.5 select-none">
        <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-3">
          PROVIDER QUOTA
        </div>

        <div className="flex flex-col gap-3.5">
          {quotas.map((q) => {
            const tagColor = q.tag === 'EXACT' ? '#3FB950' : q.tag === 'ESTIMATED' ? '#E3A008' : '#8C949F';

            return (
              <div key={q.id}>
                <div className="flex items-center justify-between mb-1.5 font-mono-code text-[11px]">
                  <span style={{ color: q.color }}>{q.name}</span>
                  <span
                    style={{ color: tagColor, borderColor: `${tagColor}44` }}
                    className="text-[10px] tracking-wider px-1.5 py-0.5 border"
                  >
                    {q.tag}
                  </span>
                </div>

                <div className="h-1.5 bg-[#14171C] relative mb-1.5">
                  <div
                    style={{
                      width: q.pct,
                      backgroundColor: q.color,
                      opacity: Number(q.opacity) || 0.8
                    }}
                    className="absolute left-0 top-0 bottom-0"
                  />
                  <div className="absolute inset-0 bg-striped-pattern pointer-events-none" />
                </div>

                <div className="flex justify-between font-mono-code text-[11px] text-[#8C949F]">
                  <span>{q.left}</span>
                  <span className="text-[#5C646E]">{q.conf}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // Full detailed card view for /usage route
  return (
    <div className="p-5 select-none">
      <div className="text-[11px] tracking-wider text-[#5C646E] font-mono-code">
        3 · PROVIDER QUOTA
      </div>
      <div className="mt-1 text-[11px] text-[#5C646E] mb-4">
        measurement fidelity varies by provider
      </div>

      <div className="flex flex-col gap-4">
        {quotas.map((q) => {
          const isEst = q.tag === 'ESTIMATED';
          const isExact = q.tag === 'EXACT';
          const tagColor = isExact ? '#3FB950' : isEst ? '#E3A008' : '#8C949F';

          return (
            <div
              key={q.id}
              style={{
                borderColor: q.tag === 'UNKNOWN' ? '#1A1E24' : '#1F242B'
              }}
              className="p-3 bg-[#101216] border"
            >
              <div className="flex items-center justify-between">
                <span style={{ color: q.color }} className="font-mono-code text-[12px] tracking-wider font-semibold">
                  {q.name}
                </span>
                <span
                  style={{
                    color: tagColor,
                    borderColor: `${tagColor}44`,
                    backgroundColor: isEst ? 'rgba(227,160,8,0.06)' : 'transparent'
                  }}
                  className="font-mono-code text-[10px] tracking-wider px-1.5 py-0.5 border"
                >
                  {q.tag}
                </span>
              </div>

              <div className="mt-1 text-[11px] text-[#5C646E]">
                {q.window}
              </div>

              <div className="mt-2.5 h-2 bg-[#14171C] relative">
                <div
                  style={{
                    width: q.pct,
                    backgroundColor: q.color,
                    opacity: Number(q.opacity) || 0.8
                  }}
                  className="absolute left-0 top-0 bottom-0"
                />
                {isEst && (
                  <div className="absolute inset-0 border border-dashed border-[rgba(227,160,8,0.35)] pointer-events-none" />
                )}
                <div className="absolute inset-0 bg-striped-pattern pointer-events-none" />
              </div>

              <div className="mt-2 flex justify-between font-mono-code text-[11px]">
                <span className="text-[#8C949F]">{q.left}</span>
                <span style={{ color: isEst ? '#E3A008' : '#5C646E' }}>{q.conf}</span>
              </div>

              <div className="mt-2 pt-2 border-t border-[#1F242B] font-mono-code text-[11px] text-[#5C646E] leading-relaxed whitespace-pre">
                {q.basis}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
