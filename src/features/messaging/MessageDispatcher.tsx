import React from 'react';

/**
 * Operator command dispatch is disabled. The Hermes API has no command endpoint, and the previous
 * form reported success without sending anything. Thread messages on a job are the real channel.
 */
export const MessageDispatcher: React.FC = () => {
  return (
    <div className="p-4 bg-[#0E1116] border border-[#1F242B] select-none">
      <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-2.5 flex items-center justify-between">
        <span>OPERATOR COMMAND</span>
        <span className="text-[#5C646E]">unavailable</span>
      </div>

      <form onSubmit={(e) => e.preventDefault()} className="flex flex-col gap-2.5">
        <div className="flex gap-2">
          <input
            type="text"
            disabled
            aria-describedby="dispatch-unavailable"
            placeholder="Operator commands are not available yet"
            className="flex-1 bg-[#12151A] border border-[#2A3038] font-mono-code text-[12px] text-[#5C646E] px-3 py-1.5 outline-none cursor-not-allowed"
          />
          <button
            type="submit"
            disabled
            title="The Hermes API has no operator command endpoint yet"
            className="font-mono-code text-[11px] px-3 py-1.5 border border-[#2A3038] text-[#5C646E] cursor-not-allowed"
          >
            DISPATCH
          </button>
        </div>
        <p id="dispatch-unavailable" className="font-mono-code text-[11px] text-[#5C646E]">
          The Hermes API has no operator command endpoint yet, so nothing is sent from here.
        </p>
      </form>
    </div>
  );
};
