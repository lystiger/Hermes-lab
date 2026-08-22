import React from 'react';
import { useConsoleStore } from '../stores/useConsoleStore';
import { JobDetailView } from '../features/jobs/JobDetailView';

export const JobModal: React.FC = () => {
  const { activeModalJobId, setActiveModalJobId } = useConsoleStore();

  if (!activeModalJobId) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-8 bg-[rgba(10,11,13,0.85)] backdrop-blur-sm select-none">
      <div className="relative w-full max-w-5xl max-h-[90vh] bg-[#0A0B0D] border border-[#2A3038] shadow-2xl flex flex-col overflow-hidden">
        {/* Modal Top Bar */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-[#0C0E11] border-b border-[#1F242B]">
          <div className="font-mono-code text-[12px] text-[#8C949F] flex items-center gap-2">
            <span className="text-[#CBA35C]">LYSCONTROL // JOB INSPECTOR</span>
            <span>·</span>
            <span>{activeModalJobId}</span>
          </div>
          <button
            onClick={() => setActiveModalJobId(null)}
            className="font-mono-code text-[12px] text-[#8C949F] hover:text-[#E6E9ED] px-2 py-0.5 border border-transparent hover:border-[#2A3038] cursor-pointer transition-colors"
          >
            ✕ CLOSE
          </button>
        </div>

        {/* Modal Content */}
        <div className="flex-1 overflow-y-auto">
          <JobDetailView jobId={activeModalJobId} />
        </div>
      </div>
    </div>
  );
};
