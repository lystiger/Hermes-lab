import React from 'react';
import { ExecutionResource } from '../../api/types';
import { Badge } from '../../components/Badge';
import { formatExpiry, stateStyle } from './executionFormat';

interface ExecutionResourceCardProps {
  resource: ExecutionResource;
  nowMs: number;
}

/** One live execution resource (seat, pane or process). Failed resources are highlighted in red. */
export const ExecutionResourceCard: React.FC<ExecutionResourceCardProps> = ({ resource, nowMs }) => {
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
        borderColor: failed ? 'rgba(242,85,90,0.55)' : '#1F242B',
        backgroundColor: failed ? 'rgba(242,85,90,0.07)' : '#101216'
      }}
      className="p-3 border font-mono-code text-[11px] flex flex-col gap-2 min-w-0"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[13px] font-sans text-[#E6E9ED] truncate" title={resource.label}>{resource.label}</div>
          <div className="text-[#5C646E] truncate" title={`${resource.kind} · ${resource.id}`}>
            {resource.kind} · {resource.id}
          </div>
        </div>
        <Badge label={style.label} color={style.color} dot pulse={resource.state === 'running'} />
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {reused && <Badge label="reused" color="#7FB3D5" />}
        {resource.details?.generation && <Badge label={`gen ${resource.details.generation}`} color="#8C949F" />}
        {releaseFailed && <Badge label="release failed" color="#F2555A" />}
        {expiry && <span className="text-[#CBA35C]">{expiry}</span>}
      </div>

      <div className="flex flex-col gap-0.5 text-[#8C949F]">
        <span className="truncate">
          job <span className="text-[#E6E9ED]">{resource.jobId || '—'}</span>
          {resource.taskId ? <> · task <span className="text-[#E6E9ED]">{resource.taskId}</span></> : null}
        </span>
        {resource.executionId && (
          <span className="truncate text-[#5C646E]" title={resource.executionId}>exec {resource.executionId}</span>
        )}
      </div>

      {failed && (errorCode || errorText) && (
        <div className="text-[#F2555A] break-words">
          {errorCode && <span className="font-semibold">{errorCode}</span>}
          {errorCode && errorText ? ' · ' : ''}
          {errorText}
        </div>
      )}
    </div>
  );
};
