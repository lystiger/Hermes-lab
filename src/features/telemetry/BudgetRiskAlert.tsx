import React from 'react';
import { useNavigate } from 'react-router-dom';

export const BudgetRiskAlert: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="p-4 border-b border-[#1F242B] bg-[rgba(227,160,8,0.05)] select-none">
      <div className="flex items-center gap-2 font-mono-code text-[11px] tracking-wider text-[#E3A008]">
        <span>⚠</span>
        <span>BUDGET RISK</span>
      </div>

      <p className="mt-2 text-[12px] text-[#D7DCE2] leading-relaxed">
        Another large Codex verification may exceed the sprint budget. #148 is projected to overrun by ~9k tokens.
      </p>

      <div className="mt-2.5 flex items-center gap-2">
        <button
          onClick={() => navigate('/usage')}
          className="font-mono-code text-[11px] text-[#E6E9ED] border border-[#2A3038] px-2.5 py-1 hover:border-[#5C646E] bg-[#101216] transition-colors cursor-pointer"
        >
          inspect budget
        </button>
        <button
          onClick={() => alert('Sprint cap raised by +50k tokens.')}
          className="font-mono-code text-[11px] text-[#8C949F] border border-[#2A3038] px-2.5 py-1 hover:border-[#5C646E] hover:text-[#E6E9ED] bg-[#101216] transition-colors cursor-pointer"
        >
          raise cap
        </button>
      </div>
    </div>
  );
};
