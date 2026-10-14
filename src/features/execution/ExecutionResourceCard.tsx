import React from 'react';
import { ExecutionResource } from '../../api/types';
import { Badge } from '../../components/Badge';
import { CopyId } from '../../components/CopyId';
import { formatExpiry, stateStyle } from './executionFormat';

interface ExecutionResourceCardProps {
  resource: ExecutionResource;
  nowMs: number;
  /** 1-based slot within its backend group, shown as the seat number. */
  seat?: number;
}

/** One live execution resource (seat, pane or process). Failed resources are highlighted in red. */
export const ExecutionResourceCard: React.FC<ExecutionResourceCardProps> = ({ resource, nowMs, seat }) => {
  const style = stateStyle(resource.state);
  const failed = resource.state === 'failed';
  const reused = resource.details?.reused === true;
  const releaseFailed = resource.details?.releaseFailed === true;
  const expiry = resource.state === 'idle' ? formatExpiry(resource.expiresAt, nowMs) : null;
  const errorText = resource.details?.error as string | undefined;
  const errorCode = resource.details?.errorCode as string | undefined;

  return (
    <div
      data-testid="execution-resource"
      data-state={resource.state}
      style={{
        borderColor: failed ? 'color-mix(in srgb, var(--lys-status-danger) 55%, transparent)' : 'var(--lys-border-subtle)',
        backgroundColor: failed ? 'color-mix(in srgb, var(--lys-status-danger) 7%, transparent)' : 'var(--lys-surface-1)'
      }}
      className="p-3 border font-mono-code text-[11px] flex flex-col gap-2 min-w-0"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[13px] font-sans text-lys-primary truncate" title={resource.label}>{resource.label}</div>
          <div className="text-lys-faint flex items-center gap-2 min-w-0">
            {seat !== undefined && <span className="text-lys-muted">SEAT {String(seat).padStart(2, '0')}</span>}
            <span className="truncate" title={`${resource.kind} · ${resource.id}`}>{resource.kind}</span>
            <CopyId value={resource.id} className="text-[10px]" />
          </div>
        </div>
        <Badge label={style.label} color={style.color} dot pulse={resource.state === 'running'} />
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {reused && <Badge label="reused" color="var(--lys-accent-sky)" />}
        {resource.details?.generation && <Badge label={`gen ${resource.details.generation}`} color="var(--lys-text-muted)" />}
        {releaseFailed && <Badge label="release failed" color="var(--lys-status-danger)" />}
        {expiry && <span className="text-lys-gold">{expiry}</span>}
      </div>

      <div className="flex flex-col gap-0.5 text-lys-muted">
        <span className="truncate">
          job <span className="text-lys-primary">{resource.jobId || '—'}</span>
          {resource.taskId ? <> · task <span className="text-lys-primary">{resource.taskId}</span></> : null}
        </span>
        {resource.executionId && (
          <span className="truncate text-lys-faint" title={resource.executionId}>exec {resource.executionId}</span>
        )}
      </div>

      {failed && (errorCode || errorText) && (
        <div className="text-lys-danger break-words">
          {errorCode && <span className="font-semibold">{errorCode}</span>}
          {errorCode && errorText ? ' · ' : ''}
          {errorText}
        </div>
      )}
    </div>
  );
};
