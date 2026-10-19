import React from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { useAgent } from '../api/hooks';
import { useConsoleStore } from '../stores/useConsoleStore';
import { isRealApiMode } from '../api/client';

export const Header: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { agentId } = useParams<{ agentId?: string }>();
  const { agent } = useAgent(agentId);
  const { connectionStatus, backendHealth } = useConsoleStore();

  const pathname = location.pathname;

  let title = '';
  let crumb = '';
  let backPath = '';

  if (pathname.startsWith('/agents/')) {
    title = agent?.displayName || agentId || 'Agent';
    crumb = 'Agents';
    backPath = '/agents';
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
          <>
            <button onClick={() => navigate(backPath)} className="text-[12px] text-lys-faint hover:text-lys-primary cursor-pointer transition-colors">
              ← {crumb}
            </button>
            <span className="text-[12px] text-lys-muted break-words" title={title}>{title}</span>
          </>
        ) : null}
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
