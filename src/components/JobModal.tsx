import React from 'react';
import { useConsoleStore } from '../stores/useConsoleStore';
import { JobDetailView } from '../features/jobs/JobDetailView';
import { useEscape } from './keyboard';
import { CopyId } from './CopyId';

export const JobModal: React.FC = () => {
  const { activeModalJobId, setActiveModalJobId } = useConsoleStore();
  // Escape closes the inspector from anywhere on the page.
  useEscape(() => setActiveModalJobId(null), activeModalJobId !== null);

  if (!activeModalJobId) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-8 bg-lys-base/85 backdrop-blur-sm select-none">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Job ${activeModalJobId}`}
        className="relative w-full max-w-5xl max-h-[90vh] bg-lys-base border border-lys-default shadow-2xl flex flex-col overflow-hidden lys-drawer"
      >
        {/* Modal Top Bar */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-lys-surface-0 border-b border-lys-subtle">
          <div className="font-sans text-[12px] text-lys-muted flex items-center gap-2">
            <span className="text-lys-gold">LYSCONTROL // JOB INSPECTOR</span>
            <span>·</span>
            <CopyId value={activeModalJobId} />
          </div>
          <button
            onClick={() => setActiveModalJobId(null)}
            className="font-sans text-[12px] text-lys-muted hover:text-lys-primary px-2 py-0.5 border border-transparent hover:border-lys-default cursor-pointer transition-colors"
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
