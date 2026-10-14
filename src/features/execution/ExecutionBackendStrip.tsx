import React from 'react';
import { ExecutionBackendStatus, OpenRigExecutionStatus } from '../../api/types';

interface ExecutionBackendStripProps {
  backends: ExecutionBackendStatus[];
  openrig: OpenRigExecutionStatus | null;
  loaded: boolean;
}

const dot = (color: string) => <span style={{ backgroundColor: color }} className="w-1.5 h-1.5 rounded-[1px]" />;

/** Backend availability strip: one cell per backend, plus the OpenRig daemon and ledger when reported. */
export const ExecutionBackendStrip: React.FC<ExecutionBackendStripProps> = ({ backends, openrig, loaded }) => {
  if (backends.length === 0 && !openrig) {
    return (
      <div className="font-mono-code text-[11px] text-[#5C646E]">
        {loaded ? 'No execution backends reported.' : 'Waiting for backend status…'}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {backends.map((b) => {
        const color = b.available ? '#3FB950' : '#F2555A';
        return (
          <div key={b.name} className="p-3 bg-[#0C0E11] border border-[#1F242B] font-mono-code text-[11px]">
            <div className="flex items-center justify-between">
              <span className="text-[#E6E9ED] font-semibold tracking-wider uppercase">{b.name}</span>
              <span style={{ color }} className="flex items-center gap-1.5">
                {dot(color)}
                {b.available ? 'AVAILABLE' : 'UNAVAILABLE'}
              </span>
            </div>
            <div className="mt-1.5 text-[#8C949F] truncate" title={b.detail}>{b.detail || '—'}</div>
          </div>
        );
      })}

      {openrig && (
        <div className="p-3 bg-[#0C0E11] border border-[#1F242B] font-mono-code text-[11px]">
          <div className="flex items-center justify-between">
            <span className="text-[#E6E9ED] font-semibold tracking-wider uppercase">openrig daemon</span>
            <span
              style={{ color: openrig.daemon === 'up' ? '#3FB950' : openrig.daemon === 'down' ? '#F2555A' : '#8C949F' }}
              className="flex items-center gap-1.5 uppercase"
            >
              {dot(openrig.daemon === 'up' ? '#3FB950' : openrig.daemon === 'down' ? '#F2555A' : '#8C949F')}
              {openrig.daemon}
            </span>
          </div>
          <div className="mt-1.5 text-[#8C949F] truncate" title={openrig.ledger.rigIds.join(', ')}>
            {openrig.ledger.owners} ledger owners · {openrig.ledger.rigIds.length} rigs
          </div>
        </div>
      )}
    </div>
  );
};
