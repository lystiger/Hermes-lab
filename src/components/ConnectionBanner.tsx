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
      className="px-5 py-2.5 border-b border-[rgba(242,85,90,0.5)] bg-[rgba(242,85,90,0.12)] font-mono-code text-[12px] text-[#F2555A] flex flex-wrap items-center gap-x-4 gap-y-1"
    >
      <span className="font-semibold tracking-wider">CAN&apos;T REACH HERMES</span>
      <span className="text-[#E6E9ED] break-all">API {conn.url}</span>
      <span className="text-[#D7DCE2]">
        last successful contact{' '}
        {conn.lastContactAt ? formatDateTime(conn.lastContactAt) : 'none this session'}
      </span>
      <button
        type="button"
        onClick={retry}
        className="ml-auto px-2.5 py-0.5 border border-[rgba(242,85,90,0.6)] text-[#E6E9ED] hover:bg-[rgba(242,85,90,0.2)] cursor-pointer"
      >
        retry
      </button>
    </div>
  );
};
