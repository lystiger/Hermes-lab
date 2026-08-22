import React from 'react';
import { AmbientGyro } from '../../components/AmbientGyro';
import { JobPipelineGraph } from './JobPipelineGraph';
import { useConsoleStore } from '../../stores/useConsoleStore';

interface ActiveExecutionCardProps {
  onOpenJob?: () => void;
}

export const ActiveExecutionCard: React.FC<ActiveExecutionCardProps> = ({ onOpenJob }) => {
  const { ambient3d, elapsed, jobTokens } = useConsoleStore();

  return (
    <div className="relative p-5 pb-6 border-b border-[#1F242B] overflow-hidden select-none bg-[#0A0B0D]">
      <AmbientGyro enabled={ambient3d} size={150} />

      {/* Header Status */}
      <div className="flex items-center gap-2.5 mb-2">
        <span className="font-mono-code text-[11px] text-[#5C646E] tracking-wider">
          ACTIVE EXECUTION
        </span>
        <span className="flex items-center gap-1.5 font-mono-code text-[11px] text-[#3FB950] border border-[rgba(63,185,80,0.35)] px-1.5 py-0.5 bg-[rgba(63,185,80,0.05)]">
          <span className="w-1 h-1 rounded-[1px] bg-[#3FB950] animate-pulse" />
          RUNNING
        </span>
      </div>

      {/* Main Title / Clickable Target */}
      <div
        onClick={onOpenJob}
        className="flex items-baseline flex-wrap gap-x-3 gap-y-0.5 cursor-pointer hover:opacity-80 transition-opacity"
      >
        <span className="font-mono-code text-[26px] text-[#5C646E]">#142</span>
        <span className="text-[22px] font-semibold tracking-tight text-[#E6E9ED]">
          Move VehicleStateStore to Redis
        </span>
      </div>

      {/* Metadata Bar */}
      <div className="flex items-center flex-wrap gap-x-3.5 gap-y-1 mt-2 font-mono-code text-[11px] text-[#8C949F]">
        <span>moveinmate/backend</span>
        <span className="text-[#2A3038]">·</span>
        <span className="text-[#CBA35C]">feat/redis-state</span>
        <span className="text-[#2A3038]">·</span>
        <span>started 10:38</span>
        <span className="text-[#2A3038]">·</span>
        <span>elapsed <span className="text-[#E6E9ED]">{elapsed}</span></span>
        <span className="text-[#2A3038]">·</span>
        <span>budget <span className="text-[#E6E9ED]">{jobTokens}</span> / 80k</span>
      </div>

      {/* 3D Pipeline Graph */}
      <div className="mt-6">
        <JobPipelineGraph />
      </div>

      {/* Estimated Completion Footer */}
      <div className="mt-5 flex flex-wrap gap-6 pt-3.5 border-t border-[#1F242B] font-mono-code text-[11px]">
        <span className="text-[#5C646E]">ESTIMATED COMPLETION</span>
        <span className="text-[#8C949F]">phase <span className="text-[#E6E9ED]">~4 min</span></span>
        <span className="text-[#8C949F]">job <span className="text-[#E6E9ED]">~11 min</span></span>
        <span className="text-[#8C949F]">queue <span className="text-[#E6E9ED]">~37 min</span></span>
        <span className="text-[#5C646E]">median of 34 runs · confidence <span className="text-[#E3A008]">medium</span></span>
      </div>
    </div>
  );
};
