import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AgentSummary } from '../../api/types';
import { AgentPortrait } from './AgentPortrait';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { UNKNOWN } from '../../components/DataStates';

interface AgentLaneCardProps {
  agent: AgentSummary;
  size?: 'compact' | 'full';
}

export const AgentLaneCard: React.FC<AgentLaneCardProps> = ({
  agent,
  size = 'compact'
}) => {
  const navigate = useNavigate();
  const { setSelectedAgentId, liveMotion } = useConsoleStore();
  const [showCtxPopup, setShowCtxPopup] = useState(false);

  const isRunning = agent.status === 'RUNNING';
  const accentColor = agent.presentation?.accentColor || '#8C949F';
  // Context figures are only shown when Hermes reports them for this agent; otherwise they are unknown.
  const contextPct = agent.contextPct ?? UNKNOWN;
  const contextUsed = agent.contextUsed ?? UNKNOWN;
  const contextMax = agent.contextMax ?? UNKNOWN;
  const hasContextPct = agent.contextPct !== undefined;

  const handleClick = () => {
    setSelectedAgentId(agent.id);
    navigate(`/agents/${agent.id}`);
  };

  if (size === 'compact') {
    return (
      <div
        onClick={handleClick}
        style={{
          backgroundColor: isRunning ? '#0E1116' : 'transparent',
          opacity: isRunning ? 1 : 0.72
        }}
        className="flex-1 min-w-[270px] p-4 border-r border-b border-[#1F242B] cursor-pointer hover:bg-[#12151A] hover:opacity-100 transition-all select-none"
      >
        <div className="flex gap-3.5">
          <AgentPortrait
            displayName={agent.displayName}
            presentation={agent.presentation}
            status={agent.status}
            phase={agent.phase}
            size="sm"
          />

          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[14px] font-semibold text-[#E6E9ED]">{agent.displayName}</span>
              <span className="font-mono-code text-[11px] text-[#5C646E] truncate max-w-[100px]">{agent.model}</span>
            </div>

            <div className="flex items-center gap-2 mt-1.5">
              <span
                style={{ backgroundColor: isRunning ? '#3FB950' : '#8C949F' }}
                className={`w-1.5 h-1.5 rounded-[1px] ${isRunning && liveMotion ? 'animate-pulse' : ''}`}
              />
              <span
                style={{ color: isRunning ? '#3FB950' : '#8C949F' }}
                className="font-mono-code text-[11px] uppercase tracking-wider"
              >
                {agent.status}
              </span>
              {agent.phase && (
                <span className="font-mono-code text-[11px] tracking-wider text-[#8C949F] border-l border-[#2A3038] pl-2">
                  {agent.phase}
                </span>
              )}
            </div>

            <p className="mt-2 text-[12px] text-[#B7BEC7] line-clamp-2 leading-relaxed">
              {agent.currentTask || agent.role}
            </p>

            <div className="mt-2.5 flex flex-wrap items-center gap-x-3.5 gap-y-1 font-mono-code text-[11px] text-[#8C949F]">
              <span>{isRunning ? 'active runtime' : 'idle'}</span>
              <span>{agent.sessionTokens ?? UNKNOWN} tokens</span>
              <span style={{ color: accentColor }}>{agent.activeTool || 'tool: —'}</span>
            </div>

            {/* Context meter */}
            <div className="mt-2.5 flex items-center gap-2">
              <div className="flex-1 h-[3px] bg-[#1F242B] relative">
                {hasContextPct && (
                  <div
                    style={{
                      width: contextPct,
                      backgroundColor: accentColor
                    }}
                    className="absolute left-0 top-0 bottom-0 opacity-85"
                  />
                )}
              </div>
              <span className="font-mono-code text-[11px] text-[#5C646E]">
                ctx {contextPct}
              </span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Full Card for /agents route
  return (
    <div
      onClick={handleClick}
      style={{ backgroundColor: '#0A0B0D' }}
      className="flex-1 min-w-[340px] flex gap-4 p-5 border-r border-b border-[#1F242B] cursor-pointer hover:bg-[#0E1116] transition-colors select-none"
    >
      <AgentPortrait
        displayName={agent.displayName}
        presentation={agent.presentation}
        status={agent.status}
        phase={agent.phase}
        size="md"
      />

      <div className="flex-1 min-w-0 flex flex-col">
        <div className="flex items-center gap-2.5">
          <span className="text-[15px] font-semibold text-[#E6E9ED]">{agent.displayName}</span>
          {agent.phase && (
            <span
              style={{
                color: accentColor,
                borderColor: `${accentColor}44`
              }}
              className="font-mono-code text-[11px] tracking-wider border px-1.5 py-0.5"
            >
              {agent.phase}
            </span>
          )}
          <span
            style={{ color: isRunning ? '#3FB950' : '#8C949F' }}
            className="flex items-center gap-1.5 font-mono-code text-[11px] tracking-wider"
          >
            <span
              style={{ backgroundColor: isRunning ? '#3FB950' : '#8C949F' }}
              className="w-1.5 h-1.5 rounded-[1px]"
            />
            {agent.status}
          </span>
        </div>

        <div className="mt-1 font-mono-code text-[11px] text-[#5C646E]">
          {agent.model} · {agent.provider}
        </div>

        {/* Hoverable Context Info */}
        <div
          onMouseEnter={() => setShowCtxPopup(true)}
          onMouseLeave={() => setShowCtxPopup(false)}
          className="relative mt-3 cursor-help"
        >
          <div className="flex items-center justify-between font-mono-code text-[11px] text-[#8C949F]">
            <span className="tracking-wider">CONTEXT WINDOW</span>
            <span className="text-[#E6E9ED]">{contextUsed} / {contextMax} ({contextPct})</span>
          </div>
          <div className="mt-1.5 h-[7px] bg-[#14171C] relative">
            {hasContextPct && (
              <div
                style={{ width: contextPct, backgroundColor: accentColor }}
                className="absolute left-0 top-0 bottom-0 opacity-90"
              />
            )}
            <div className="absolute inset-0 bg-striped-pattern pointer-events-none" />
          </div>

          {showCtxPopup && (
            <div className="absolute left-0 top-full mt-2 z-30 w-64 p-3 bg-[#12151A] border border-[#2A3038] shadow-2xl font-mono-code text-[11px] text-[#B7BEC7] leading-relaxed">
              <div className="font-semibold text-[#E6E9ED] pb-1 border-b border-[#2A3038] mb-1.5">Context Window Allocation</div>
              <div>• Used: {contextUsed} ({contextPct})</div>
              <div>• Total Cap: {contextMax}</div>
              <div>• Capabilities: {agent.capabilities.join(', ')}</div>
            </div>
          )}
        </div>

        <p className="mt-3 text-[12px] text-[#B7BEC7] line-clamp-2 leading-relaxed font-sans">
          {agent.currentTask || agent.role}
        </p>

        <div className="flex-1 min-h-3" />

        {/* Bottom Quick Stats */}
        <div className="grid grid-cols-4 gap-2 pt-3 border-t border-[#1F242B]">
          <div>
            <div className="text-[11px] text-[#5C646E] tracking-wider font-mono-code">QUEUE</div>
            <div className="font-mono-code text-[13px] text-[#E6E9ED] mt-0.5">{agent.queueDepth ?? UNKNOWN}</div>
          </div>
          <div>
            <div className="text-[11px] text-[#5C646E] tracking-wider font-mono-code">SESSION</div>
            <div className="font-mono-code text-[13px] text-[#E6E9ED] mt-0.5">{agent.sessionTokens ?? UNKNOWN}</div>
          </div>
          <div>
            <div className="text-[11px] text-[#5C646E] tracking-wider font-mono-code">STATUS</div>
            <div className="font-mono-code text-[13px] text-[#3FB950] mt-0.5">{agent.status}</div>
          </div>
          <div>
            <div className="text-[11px] text-[#5C646E] tracking-wider font-mono-code">ROLE</div>
            <div className="font-mono-code text-[13px] text-[#8C949F] mt-0.5 truncate">{agent.capabilities[0] || 'agent'}</div>
          </div>
        </div>
      </div>
    </div>
  );
};
