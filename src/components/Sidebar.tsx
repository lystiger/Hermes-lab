import React from 'react';
import { NavLink } from 'react-router-dom';
import { AnimatedCube } from './AnimatedCube';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useExecutionStore } from '../stores/useExecutionStore';
import { useAgents, useJobs } from '../api/hooks';
import { ConnectionStatus } from '../api/types';

interface NavItem {
  to: string;
  label: string;
  badge?: string;
  badgeColor?: string;
}

// Jobs that have not reached a terminal state: the work the queue still holds.
const TERMINAL_JOB_STATUSES = ['COMPLETED', 'FAILED', 'CANCELLED'];

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Overview' },
  { to: '/queue', label: 'Queue' },
  { to: '/agents', label: 'Agents' },
  { to: '/usage', label: 'Usage' },
  { to: '/events', label: 'Events' },
  { to: '/execution', label: 'Execution' },
  { to: '/settings', label: 'Settings' }
];

const CONNECTION_LABEL: Record<ConnectionStatus, { text: string; color: string }> = {
  CONNECTED: { text: 'Reachable', color: 'var(--lys-status-success)' },
  CONNECTING: { text: 'Connecting', color: 'var(--lys-status-warning)' },
  DEGRADED: { text: 'Degraded', color: 'var(--lys-status-warning)' },
  DISCONNECTED: { text: 'Unreachable', color: 'var(--lys-status-danger)' }
};

export const Sidebar: React.FC = () => {
  const { clock, connectionStatus } = useConsoleStore();
  const resources = useExecutionStore((s) => s.view.resources);
  const herdr = useExecutionStore((s) => s.view.backends.find((b) => b.name === 'herdr'));
  const snapshotStatus = useExecutionStore((s) => s.snapshotStatus);
  const { jobs, error: jobsError } = useJobs();
  const { agents, error: agentsError } = useAgents();

  // Execution badge: resources currently acquiring or running (live from the D-009 snapshot + events).
  const activeCount = Object.values(resources).filter((r) => r.state === 'acquiring' || r.state === 'running').length;
  // Badges are real counts from the loaded lists; a list that failed to load shows no badge rather than a guess.
  const queueCount = jobs.filter((j) => !TERMINAL_JOB_STATUSES.includes(j.status)).length;
  const badges: Record<string, { badge: string; badgeColor?: string } | undefined> = {
    '/queue': !jobsError && jobs.length > 0 ? { badge: String(queueCount) } : undefined,
    '/agents': !agentsError && agents.length > 0 ? { badge: String(agents.length) } : undefined,
    '/events': connectionStatus === 'CONNECTED' ? { badge: 'live', badgeColor: 'var(--lys-status-success)' } : undefined,
    '/execution': activeCount > 0 ? { badge: String(activeCount), badgeColor: 'var(--lys-status-success)' } : undefined
  };
  const navItems = NAV_ITEMS.map((item) => ({ ...item, ...badges[item.to] }));

  // "Available" means the herdr executable is on PATH. It does not mean a running sandbox.
  const herdrStatus = herdr
    ? herdr.available
      ? { text: 'Available', color: 'var(--lys-status-success)' }
      : { text: 'Unavailable', color: 'var(--lys-status-danger)' }
    : { text: snapshotStatus === 'error' ? 'Unknown' : '—', color: 'var(--lys-text-muted)' };
  const hermesStatus = CONNECTION_LABEL[connectionStatus];

  return (
    <aside className="w-52 flex-shrink-0 bg-lys-surface-0 border-r border-lys-subtle flex flex-col py-4 select-none">
      {/* Brand Header */}
      <div className="flex items-center gap-2.5 px-4 pb-4.5">
        <AnimatedCube size={26} />
        <div className="text-[12px] font-bold tracking-[0.16em] text-lys-primary">
          LYSCONTROL
        </div>
      </div>

      {/* Nav List */}
      <nav className="flex flex-col gap-0.5 mt-1">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) => `
              flex items-center justify-between px-4 py-2 text-[13px] transition-colors border-l-2
              ${isActive 
                ? 'border-lys-gold bg-lys-surface-1 text-lys-primary' 
                : 'border-transparent text-lys-muted hover:bg-lys-surface-1 hover:text-lys-primary'}
            `}
          >
            <span>{item.label}</span>
            {item.badge && (
              <span
                style={{ color: item.badgeColor || 'var(--lys-text-faint)' }}
                className="font-mono-code text-[11px]"
              >
                {item.badge}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="flex-1" />

      {/* Daemon & Health Monitor */}
      <div className="border-t border-lys-subtle mx-0 px-4 pt-3 flex flex-col gap-1.5">
        <div className="flex items-center justify-between font-mono-code text-[11px] text-lys-muted" title="Connection to the Hermes runtime API">
          <span>Hermes</span>
          <span style={{ color: hermesStatus.color }} className="flex items-center gap-1.5">
            <span style={{ backgroundColor: hermesStatus.color }} className="w-1.5 h-1.5" />
            {hermesStatus.text}
          </span>
        </div>
        <div className="flex items-center justify-between font-mono-code text-[11px] text-lys-muted" title={herdr?.detail}>
          <span>Herdr</span>
          <span style={{ color: herdrStatus.color }} className="flex items-center gap-1.5">
            <span style={{ backgroundColor: herdrStatus.color }} className="w-1.5 h-1.5" />
            {herdrStatus.text}
          </span>
        </div>
        <div className="flex items-center justify-between font-mono-code text-[11px] text-lys-faint pt-1">
          <span>v0.1.0</span>
          <span>{clock}</span>
        </div>
      </div>
    </aside>
  );
};
