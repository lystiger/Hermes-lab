import React from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { useAgent, useAgents } from '../api/hooks';
import { useConsoleStore } from '../stores/useConsoleStore';
import { isRealApiMode } from '../api/client';

export const Header: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { agentId } = useParams<{ agentId?: string }>();
  const { agent } = useAgent(agentId);
  const { agents } = useAgents();
  const { connectionStatus, backendHealth } = useConsoleStore();

  const pathname = location.pathname;

  let title = 'Overview';
  let subtitle = isRealApiMode ? 'hermes · runtime API' : 'hermes · local runtime';
  let crumb = '';
  let backPath = '';

  if (pathname === '/') {
    title = 'Overview';
    subtitle = isRealApiMode ? 'hermes · runtime API' : 'hermes · local runtime';
  } else if (pathname === '/queue') {
    title = 'Queue';
    subtitle = 'job queue · latest jobs from Hermes';
  } else if (pathname === '/agents') {
    title = 'Agents';
    subtitle = `${agents.length} operators registered`;
  } else if (pathname.startsWith('/agents/')) {
    title = agent?.displayName || agentId || 'Agent';
    subtitle = agent ? `${agent.model} · ${agent.role}` : 'Operator Inspection';
    crumb = 'Agents';
    backPath = '/agents';
  } else if (pathname === '/usage') {
    title = 'Usage';
    subtitle = 'tokens · budget · quota';
  } else if (pathname === '/events') {
    title = 'Events';
    subtitle = isRealApiMode ? 'live SSE stream' : 'trace stream';
  } else if (pathname === '/execution') {
    title = 'Execution';
    subtitle = 'every backend · snapshot + live events';
  } else if (pathname === '/settings') {
    title = 'Settings';
    subtitle = isRealApiMode ? 'Hermes REST/SSE API' : 'local';
  }

  const getConnectionColor = () => {
    switch (connectionStatus) {
      case 'CONNECTED':
        return 'var(--lys-status-success)';
      case 'CONNECTING':
        return 'var(--lys-status-warning)';
      case 'DEGRADED':
        return 'var(--lys-status-warning)';
      case 'DISCONNECTED':
        return 'var(--lys-status-danger)';
      default:
        return 'var(--lys-text-muted)';
    }
  };

  const statusColor = getConnectionColor();
  const statusLabel = isRealApiMode
    ? connectionStatus.toLowerCase()
    : 'mock mode';
  const notMeasured = 'Not reported by the Hermes API';

  return (
    <header className="h-[44px] flex-shrink-0 flex items-center justify-between px-5 border-b border-lys-subtle bg-lys-base select-none">
      <div className="flex items-center gap-3 min-w-0">
        {crumb ? (
          <button onClick={() => navigate(backPath)} className="text-[12px] text-lys-faint hover:text-lys-primary cursor-pointer transition-colors">
            ← {crumb}
          </button>
        ) : (
          <span className="text-[12px] text-lys-faint break-words" title={subtitle}>{subtitle}</span>
        )}
        {crumb && <span className="text-[12px] text-lys-muted break-words" title={title}>{title}</span>}
      </div>

      <div className="flex items-center gap-4 text-[12px] text-lys-muted">
        <span
          style={{ color: statusColor }}
          className="flex items-center gap-1.5"
          title={backendHealth ? `${backendHealth.service} v${backendHealth.version} (${backendHealth.uptimeSeconds}s uptime)` : notMeasured}
        >
          <span style={{ backgroundColor: statusColor }} className="w-1.5 h-1.5 rounded-full" />
          {statusLabel}
        </span>
      </div>
    </header>
  );
};

export default Header;
