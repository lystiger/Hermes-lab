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
  let subtitle = isRealApiMode ? 'lysstack · control plane' : 'hermes · local runtime';
  let crumb = '';
  let backPath = '';

  if (pathname === '/') {
    title = 'Overview';
    subtitle = isRealApiMode ? 'lysstack · control plane' : 'hermes · local runtime';
  } else if (pathname === '/queue') {
    title = 'Queue';
    subtitle = '8 jobs · serial per repository';
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
  } else if (pathname === '/settings') {
    title = 'Settings';
    subtitle = isRealApiMode ? 'control plane api' : 'local';
  }

  const getConnectionColor = () => {
    switch (connectionStatus) {
      case 'CONNECTED':
        return '#3FB950';
      case 'CONNECTING':
        return '#E3A008';
      case 'DEGRADED':
        return '#E3A008';
      case 'DISCONNECTED':
        return '#F2555A';
      default:
        return '#8C949F';
    }
  };

  const statusColor = getConnectionColor();
  const statusLabel = isRealApiMode
    ? connectionStatus.toLowerCase()
    : 'mock mode';

  return (
    <header className="h-[46px] flex-shrink-0 flex items-center justify-between px-5 border-b border-[#1F242B] bg-[#0C0E11] select-none">
      <div className="flex items-center gap-3">
        {crumb && (
          <button
            onClick={() => navigate(backPath)}
            className="font-mono-code text-[11px] text-[#5C646E] hover:text-[#E6E9ED] cursor-pointer transition-colors"
          >
            ← {crumb}
          </button>
        )}
        <h1 className="text-[14px] font-semibold tracking-wide text-[#E6E9ED]">
          {title}
        </h1>
        <span className="font-mono-code text-[11px] text-[#5C646E]">
          {subtitle}
        </span>
      </div>

      <div className="flex items-center gap-4 font-mono-code text-[11px] text-[#8C949F]">
        <span>queue eta <span className="text-[#E6E9ED]">~37 min</span></span>
        <span className="text-[#2A3038]">|</span>
        <span>budget <span className="text-[#E3A008]">58%</span></span>
        <span className="text-[#2A3038]">|</span>
        <span
          style={{ color: statusColor }}
          className="flex items-center gap-1.5"
          title={backendHealth ? `${backendHealth.service} v${backendHealth.version} (${backendHealth.uptimeSeconds}s uptime)` : 'Connection State'}
        >
          <span
            style={{ backgroundColor: statusColor }}
            className={`w-1.5 h-1.5 rounded-[1px] ${connectionStatus === 'CONNECTING' ? 'animate-pulse' : ''}`}
          />
          {statusLabel}
        </span>
      </div>
    </header>
  );
};

export default Header;
