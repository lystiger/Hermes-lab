import React from 'react';

export const TokenBudgetMeter: React.FC = () => {
  return (
    <div className="p-5 border-r border-[#1F242B] select-none bg-[#0A0B0D]">
      <div className="text-[11px] tracking-wider text-[#5C646E] font-mono-code">
        2 · RUN BUDGET
      </div>
      <div className="mt-1 text-[11px] text-[#5C646E]">
        controlled by LysControl policy
      </div>

      <div className="mt-4 flex items-baseline gap-2 font-mono-code">
        <span className="text-[28px] text-[#E6E9ED]">173k</span>
        <span className="text-[13px] text-[#5C646E]">/ 300k</span>
      </div>

      <div className="mt-3 h-2.5 bg-[#14171C] relative">
        <div className="absolute left-0 top-0 bottom-0 w-[58%] bg-[#E3A008]" />
        <div className="absolute inset-0 bg-striped-pattern pointer-events-none" />
        {/* Hard stop marker */}
        <div className="absolute left-[82%] -top-[3px] -bottom-[3px] w-[1px] bg-[#F2555A]" />
      </div>

      <div className="mt-1.5 font-mono-code text-[11px] text-[#5C646E]">
        marker: projected completion at 246k
      </div>

      <div className="mt-4 flex flex-col gap-1.5 font-mono-code text-[11px]">
        <div className="flex justify-between text-[#8C949F]">
          <span>sprint</span>
          <span className="text-[#E6E9ED]">redis-state · 6 jobs</span>
        </div>
        <div className="flex justify-between text-[#8C949F]">
          <span>projected completion</span>
          <span className="text-[#E6E9ED]">246k</span>
        </div>
        <div className="flex justify-between text-[#8C949F]">
          <span>projected spare</span>
          <span className="text-[#3FB950]">54k</span>
        </div>
        <div className="flex justify-between text-[#8C949F]">
          <span>hard stop policy</span>
          <span className="text-[#F2555A]">pause at 246k</span>
        </div>
      </div>
    </div>
  );
};
