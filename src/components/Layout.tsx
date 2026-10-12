import React from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { JobModal } from './JobModal';
import { DossierModal } from './DossierModal';
import { useEventStream } from '../api/hooks';

export const Layout: React.FC = () => {
  // Mount Hermes event stream subscription (legacy LysStackApi client name)
  useEventStream();

  return (
    <div className="flex h-screen min-h-screen bg-[#0A0B0D] text-[#E6E9ED] text-[13px] overflow-hidden">
      {/* Left Navigation Sidebar */}
      <Sidebar />

      {/* Main Content Area */}
      <main className="flex-1 min-w-0 flex flex-col overflow-hidden bg-[#0A0B0D]">
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
