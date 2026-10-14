import React from 'react';

/**
 * Operator command dispatch is disabled. The Hermes API has no command endpoint, and the previous
 * form reported success without sending anything. Thread messages on a job are the real channel.
 */
export const MessageDispatcher: React.FC = () => {
  return (
    <div className="p-4 bg-lys-surface-0 border border-lys-subtle select-none">
      <div className="font-mono-code text-[11px] tracking-wider text-lys-faint mb-2.5 flex items-center justify-between">
        <span>OPERATOR COMMAND</span>
        <span className="text-lys-faint">unavailable</span>
      </div>

      <form onSubmit={(e) => e.preventDefault()} className="flex flex-col gap-2.5">
        <div className="flex gap-2">
          <input
            type="text"
            disabled
            aria-describedby="dispatch-unavailable"
            placeholder="Operator commands are not available yet"
            className="flex-1 bg-lys-surface-1 border border-lys-default font-mono-code text-[12px] text-lys-faint px-3 py-1.5 outline-none cursor-not-allowed"
          />
          <button
            type="submit"
            disabled
            title="The Hermes API has no operator command endpoint yet"
            className="font-mono-code text-[11px] px-3 py-1.5 border border-lys-default text-lys-faint cursor-not-allowed"
          >
            DISPATCH
          </button>
        </div>
        <p id="dispatch-unavailable" className="font-mono-code text-[11px] text-lys-faint">
          The Hermes API has no operator command endpoint yet, so nothing is sent from here.
        </p>
      </form>
    </div>
  );
};
