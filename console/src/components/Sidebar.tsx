import React, { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { Activity, Cpu, Gauge, LayoutDashboard, LayoutGrid, ListChecks, MessageSquare, Palette, PanelLeftClose, PanelLeftOpen, ScrollText, Settings, Users, type LucideIcon } from 'lucide-react';
import { Icon } from './Icon';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useExecutionStore } from '../stores/useExecutionStore';
import { useAgents, useJobs } from '../api/hooks';
import { ConnectionStatus } from '../api/types';
import { isRealApiMode } from '../api/client';
import { TERMINAL_JOB_STATUSES } from '../api/adapters/httpAdapter';
import { isEditableTarget, readSidebarCollapsed, SIDEBAR_NARROW_QUERY, writeSidebarCollapsed } from './sidebarState';
import { useMediaQuery } from './useMediaQuery';

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  badge?: string;
  badgeColor?: string;
}

// Jobs that have not reached a terminal state: the work the queue still holds.

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/queue', label: 'Queue', icon: ListChecks },
  { to: '/agents', label: 'Agents', icon: Users },
  { to: '/usage', label: 'Usage', icon: Gauge },
  { to: '/events', label: 'Events', icon: ScrollText },
  { to: '/execution', label: 'Execution', icon: Cpu },
  { to: '/comms', label: 'Comms', icon: MessageSquare },
  { to: '/design', label: 'Design', icon: Palette },
  { to: '/floor', label: 'Floor', icon: LayoutGrid },
  { to: '/settings', label: 'Settings', icon: Settings }
];

const CONNECTION_LABEL: Record<ConnectionStatus, { text: string; color: string }> = {
  CONNECTED: { text: 'Reachable', color: 'var(--lys-status-success)' },
  CONNECTING: { text: 'Connecting', color: 'var(--lys-status-warning)' },
  DEGRADED: { text: 'Degraded', color: 'var(--lys-status-warning)' },
  DISCONNECTED: { text: 'Unreachable', color: 'var(--lys-status-danger)' }
};

/**
 * Sidebar with collapse and expand (M7 item 3). The "[" key toggles it. The choice is remembered. Below 1100px it
 * starts collapsed; the user may open it there for the current view.
 */
export const Sidebar: React.FC = () => {
  const { connectionStatus, backendHealth } = useConsoleStore();
  const resources = useExecutionStore((s) => s.view.resources);
  const herdr = useExecutionStore((s) => s.view.backends.find((b) => b.name === 'herdr'));
  const snapshotStatus = useExecutionStore((s) => s.snapshotStatus);
  const { jobs, error: jobsError } = useJobs();
  const { agents, error: agentsError } = useAgents();

  const narrow = useMediaQuery(SIDEBAR_NARROW_QUERY);
  const [pref, setPref] = useState<boolean>(() => readSidebarCollapsed() ?? false);
  const [openOnNarrow, setOpenOnNarrow] = useState(false);
  const collapsed = narrow ? !openOnNarrow : pref;

  const toggle = () => {
    if (narrow) {
      setOpenOnNarrow((open) => !open);
      return;
    }
    const next = !pref;
    setPref(next);
    writeSidebarCollapsed(next);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== '[' || e.ctrlKey || e.metaKey || e.altKey) return;
      if (isEditableTarget(e.target)) return;
      e.preventDefault();
      toggle();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  });

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
  const hermesTooltip = !isRealApiMode
    ? 'Mock mode: data is not from the Hermes API'
    : backendHealth
      ? `Connection to the Hermes runtime API · ${backendHealth.service} v${backendHealth.version} (${backendHealth.uptimeSeconds}s uptime)`
      : 'Connection to the Hermes runtime API · not reported by the Hermes API';

  return (
    <aside
      id="app-sidebar"
      aria-label="Primary"
      data-collapsed={collapsed ? 'true' : 'false'}
      className={`${collapsed ? 'w-14' : 'w-52'} flex-shrink-0 bg-lys-surface-0 border-r border-lys-subtle flex flex-col py-3 select-none transition-[width] duration-(--lys-duration-fast)`}
    >
      {/* Brand Header and toggle */}
      <div className={`flex items-center ${collapsed ? 'justify-center' : 'justify-between'} gap-2.5 px-3 pb-3`}>
        {!collapsed && (
          <div className="flex items-center gap-2.5 min-w-0 pl-1">
            <div className="text-[12px] font-bold tracking-[0.16em] text-lys-primary truncate" title="LysControl">
              LYSCONTROL
            </div>
          </div>
        )}
        <button
          type="button"
          onClick={toggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!collapsed}
          aria-controls="app-sidebar"
          title={`${collapsed ? 'Expand' : 'Collapse'} sidebar ([)`}
          className="p-1.5 text-lys-muted hover:text-lys-primary hover:bg-lys-surface-1 cursor-pointer"
        >
          <Icon icon={collapsed ? PanelLeftOpen : PanelLeftClose} label={undefined} size={16} />
        </button>
      </div>

      {/* Nav List */}
      <nav aria-label="Pages" className="flex flex-col gap-0.5 mt-1">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            title={collapsed ? item.label : undefined}
            aria-label={collapsed ? item.label : undefined}
            className={({ isActive }) => `
              flex items-center ${collapsed ? 'justify-center' : 'justify-between'} gap-2 px-3 py-2 text-[13px] transition-colors border-l-2
              ${isActive
                ? 'border-lys-gold bg-lys-surface-1 text-lys-primary'
                : 'border-transparent text-lys-muted hover:bg-lys-surface-1 hover:text-lys-primary'}
            `}
          >
            <span className="flex items-center gap-2.5 min-w-0">
              <Icon icon={item.icon} size={16} />
              {!collapsed && <span className="truncate" title={item.label}>{item.label}</span>}
            </span>
            {item.badge && !collapsed && (
              <span style={{ color: item.badgeColor || 'var(--lys-text-faint)' }} className="text-[11px] lys-metric shrink-0">
                {item.badge}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="flex-1" />

      {/* Daemon & Health Monitor */}
      <div className="border-t border-lys-subtle px-3 pt-3 flex flex-col gap-1.5">
        {collapsed ? (
          <div className="flex flex-col items-center gap-2 pb-2" aria-label={`Hermes ${hermesStatus.text}, Herdr ${herdrStatus.text}`}>
            <span title={`Hermes: ${hermesStatus.text}`} style={{ color: hermesStatus.color }} className="inline-flex">
              <Icon icon={Activity} label={`Hermes ${hermesStatus.text}`} size={14} />
            </span>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between text-[11px] text-lys-muted" title={hermesTooltip}>
              <span>Hermes</span>
              <span style={{ color: hermesStatus.color }} className="flex items-center gap-1.5">
                <span style={{ backgroundColor: hermesStatus.color }} className="w-1.5 h-1.5" />
                {hermesStatus.text}
              </span>
            </div>
            <div className="flex items-center justify-between text-[11px] text-lys-muted" title={herdr?.detail}>
              <span>Herdr</span>
              <span style={{ color: herdrStatus.color }} className="flex items-center gap-1.5">
                <span style={{ backgroundColor: herdrStatus.color }} className="w-1.5 h-1.5" />
                {herdrStatus.text}
              </span>
            </div>
          </>
        )}
      </div>
    </aside>
  );
};
