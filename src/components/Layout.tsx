import React from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { JobModal } from './JobModal';
import { DossierModal } from './DossierModal';
import { useEventStream, useExecutionSnapshotLoader } from '../api/hooks';
import { isMockMode } from '../api/client';

export const Layout: React.FC = () => {
  // Mount the Hermes event stream subscription.
  useEventStream();
  // Initial D-009 execution snapshot (live events are applied by the stream).
  useExecutionSnapshotLoader();

  return (
    <div className="flex h-screen min-h-screen bg-[#0A0B0D] text-[#E6E9ED] text-[13px] overflow-hidden">
      {/* Left Navigation Sidebar */}
      <Sidebar />

      {/* Main Content Area */}
      <main className="flex-1 min-w-0 flex flex-col overflow-hidden bg-[#0A0B0D]">
        {/* Persistent while mock fixtures are in use (VITE_LYSCONTROL_MOCK=1); never shown against live data. */}
        {isMockMode && (
          <div role="status" className="px-5 py-1.5 border-b border-[#3A2F12] bg-[rgba(227,160,8,0.12)] font-mono-code text-[11px] tracking-wider text-[#E3A008]">
            MOCK DATA · fixtures, not live Hermes data
          </div>
        )}
        <Header />
        
        <div className="flex-1 min-h-0 overflow-y-auto">
          <Outlet />
        </div>
      </main>

      {/* Modals */}
      <JobModal />
      <DossierModal />
    </div>
  );
};
