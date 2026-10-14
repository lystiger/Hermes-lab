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
      <div className="font-mono-code text-[11px] text-lys-faint">
        {loaded ? 'No execution backends reported.' : 'Waiting for backend status…'}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {backends.map((b) => {
        const color = b.available ? 'var(--lys-status-success)' : 'var(--lys-status-danger)';
        return (
          <div key={b.name} className="p-3 bg-lys-surface-0 border border-lys-subtle font-mono-code text-[11px]">
            <div className="flex items-center justify-between">
              <span className="text-lys-primary font-semibold tracking-wider uppercase">{b.name}</span>
              <span style={{ color }} className="flex items-center gap-1.5">
                {dot(color)}
                {b.available ? 'AVAILABLE' : 'UNAVAILABLE'}
              </span>
            </div>
            <div className="mt-1.5 text-lys-muted truncate" title={b.detail}>{b.detail || '—'}</div>
          </div>
        );
      })}

      {openrig && (
        <div className="p-3 bg-lys-surface-0 border border-lys-subtle font-mono-code text-[11px]">
          <div className="flex items-center justify-between">
            <span className="text-lys-primary font-semibold tracking-wider uppercase">openrig daemon</span>
            <span
              style={{ color: openrig.daemon === 'up' ? 'var(--lys-status-success)' : openrig.daemon === 'down' ? 'var(--lys-status-danger)' : 'var(--lys-text-muted)' }}
              className="flex items-center gap-1.5 uppercase"
            >
              {dot(openrig.daemon === 'up' ? 'var(--lys-status-success)' : openrig.daemon === 'down' ? 'var(--lys-status-danger)' : 'var(--lys-text-muted)')}
              {openrig.daemon}
            </span>
          </div>
          <div className="mt-1.5 text-lys-muted truncate" title={openrig.ledger.rigIds.join(', ')}>
            {openrig.ledger.owners} ledger owners · {openrig.ledger.rigIds.length} rigs
          </div>
        </div>
      )}
    </div>
  );
};
