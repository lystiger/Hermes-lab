import React from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { JobModal } from './JobModal';
import { DossierModal } from './DossierModal';
import { useEventStream, useExecutionSnapshotLoader } from '../api/hooks';
import { isMockMode } from '../api/client';
import { ConnectionBanner } from './ConnectionBanner';

export const Layout: React.FC = () => {
  // Mount the Hermes event stream subscription.
  useEventStream();
  // Initial D-009 execution snapshot (live events are applied by the stream).
  useExecutionSnapshotLoader();

  return (
    <div className="flex h-screen min-h-screen bg-lys-base text-lys-primary text-[13px] overflow-hidden">
      {/* Left Navigation Sidebar */}
      <Sidebar />

      {/* Main Content Area */}
      <main className="flex-1 min-w-0 flex flex-col overflow-hidden bg-lys-surface-0">
        {/* Persistent while mock fixtures are in use (VITE_LYSCONTROL_MOCK=1); never shown against live data. */}
        {isMockMode && (
          <div role="status" className="px-5 py-1.5 border-b border-lys-subtle bg-lys-warning/12 font-sans text-[11px] tracking-wider text-lys-warning">
            MOCK DATA · fixtures, not live Hermes data
          </div>
        )}
        <ConnectionBanner />
        <Header />
        
        <div className="lys-scroll flex-1 min-h-0 overflow-y-auto">
          <Outlet />
        </div>
      </main>

      {/* Modals */}
      <JobModal />
      <DossierModal />
    </div>
  );
};
