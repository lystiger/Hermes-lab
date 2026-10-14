import React from 'react';
import { useConnection } from '../api/connection';
import { formatDateTime } from '../features/time/format';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useExecutionStore } from '../stores/useExecutionStore';

/**
 * Shown whenever Hermes cannot be reached. It names the API URL, the last successful contact and offers a retry.
 * Retry re-requests everything the console depends on; the banner clears on the next successful response.
 */
export const ConnectionBanner: React.FC = () => {
  const conn = useConnection();
  if (conn.reachable) return null;

  const retry = () => {
    useConsoleStore.getState().markRuntimeResynced();
    void useExecutionStore.getState().refreshSnapshot();
  };

  return (
    <div
      role="alert"
      className="px-5 py-2.5 border-b border-lys-danger/50 bg-lys-danger/12 font-sans text-[12px] text-lys-danger flex flex-wrap items-center gap-x-4 gap-y-1"
    >
      <span className="font-semibold tracking-wider">CAN&apos;T REACH HERMES</span>
      <span className="text-lys-primary break-all">API {conn.url}</span>
      <span className="text-lys-primary">
        last successful contact{' '}
        {conn.lastContactAt ? formatDateTime(conn.lastContactAt) : 'none this session'}
      </span>
      <button
        type="button"
        onClick={retry}
        className="ml-auto px-2.5 py-0.5 border border-lys-danger/60 text-lys-primary hover:bg-lys-danger/20 cursor-pointer"
      >
        retry
      </button>
    </div>
  );
};
