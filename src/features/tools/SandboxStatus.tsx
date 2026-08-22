import React from 'react';

export const SandboxStatus: React.FC = () => {
  return (
    <div className="p-4 bg-[#101216] border border-[#1F242B] select-none font-mono-code text-[11px]">
      <div className="flex items-center justify-between text-[#5C646E] mb-3">
        <span className="tracking-wider">HERDR SANDBOX RUNTIME</span>
        <span className="text-[#3FB950] flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[#3FB950] animate-pulse" />
          CONTAINER READY
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-2 bg-[#0C0E11] border border-[#1A1E24]">
          <div className="text-[#5C646E]">Engine</div>
          <div className="text-[#E6E9ED] mt-0.5 font-semibold">Docker / containerd</div>
        </div>
        <div className="p-2 bg-[#0C0E11] border border-[#1A1E24]">
          <div className="text-[#5C646E]">State Store</div>
          <div className="text-[#E6E9ED] mt-0.5 font-semibold">redis://:6379 (OK)</div>
        </div>
        <div className="p-2 bg-[#0C0E11] border border-[#1A1E24]">
          <div className="text-[#5C646E]">Isolation</div>
          <div className="text-[#E6E9ED] mt-0.5 font-semibold">gVisor / seccomp</div>
        </div>
        <div className="p-2 bg-[#0C0E11] border border-[#1A1E24]">
          <div className="text-[#5C646E]">Network</div>
          <div className="text-[#E6E9ED] mt-0.5 font-semibold">bridge (host-gated)</div>
        </div>
      </div>
    </div>
  );
};
