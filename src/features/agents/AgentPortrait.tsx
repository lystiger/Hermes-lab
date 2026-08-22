import React, { useState } from 'react';
import { AgentData } from '../../api/types';
import { useConsoleStore } from '../../stores/useConsoleStore';

interface AgentPortraitProps {
  agent: AgentData;
  size?: 'sm' | 'md' | 'lg';
  showCode?: boolean;
}

export const AgentPortrait: React.FC<AgentPortraitProps> = ({
  agent,
  size = 'md',
  showCode = true
}) => {
  const { liveMotion, portraits } = useConsoleStore();
  const [imgError, setImgError] = useState(false);

  const dimClasses = {
    sm: 'w-[68px] h-[86px]',
    md: 'w-[116px] h-[148px]',
    lg: 'w-[200px] h-[256px]'
  }[size];

  const showSlot = portraits === 'both' || portraits === 'slots';
  const showMark = (portraits === 'marks' || imgError) && portraits !== 'slots';

  const scanAnimClass = size === 'lg' ? 'lys-scan-tall' : size === 'md' ? 'lys-scan-mid' : 'lys-scan';
  const isRunning = agent.status === 'RUNNING';

  return (
    <div
      style={{ perspective: size === 'lg' ? '900px' : size === 'md' ? '640px' : '420px' }}
      className="flex-shrink-0"
    >
      <div
        style={{
          transformStyle: 'preserve-3d',
          animation: liveMotion ? (agent.name === 'Gemini' ? 'lys-breathe-quick 3.2s ease-in-out infinite' : agent.name === 'Codex' ? 'lys-breathe-slow 11s ease-in-out infinite' : 'lys-breathe 7s ease-in-out infinite') : 'none'
        }}
        className={`relative ${dimClasses} transition-transform duration-300 hover:rotate-y-[-11deg] hover:rotate-x-[5deg] hover:translate-z-[10px]`}
      >
        <div
          style={{
            borderColor: isRunning ? `${agent.color}66` : '#1F242B',
            backgroundColor: '#0E1116'
          }}
          className="absolute inset-0 border overflow-hidden flex flex-col"
        >
          {/* Crawl Code Background */}
          {showCode && (
            <div className="absolute inset-0 opacity-[0.13] overflow-hidden pointer-events-none">
              <div
                style={{
                  color: agent.color,
                  animation: liveMotion ? 'lys-crawl 12s linear infinite' : 'none'
                }}
                className="font-mono-code text-[8px] leading-[10px] whitespace-pre"
              >
                {agent.crawlCode + agent.crawlCode}
              </div>
            </div>
          )}

          {/* WebP Image Portrait / Canvas Sigil */}
          <div className="relative flex-1 min-h-0 overflow-hidden flex items-center justify-center">
            {showSlot && !imgError ? (
              <img
                src={agent.avatarUrl}
                alt={`${agent.name} Portrait`}
                onError={() => setImgError(true)}
                className="w-full h-full object-cover select-none pointer-events-none"
              />
            ) : null}

            {/* Fallback Cybernetic Geometric Sigil */}
            {(showMark || imgError) && (
              <div className="absolute inset-0 flex items-end justify-center pb-2">
                <div className="relative w-[50%] h-[75%]">
                  <div
                    style={{
                      borderColor: agent.color,
                      backgroundColor: `${agent.color}22`
                    }}
                    className="absolute left-[20%] top-[10%] w-[60%] h-[40%] border clip-hex"
                  />
                  <div
                    style={{ backgroundColor: agent.color }}
                    className="absolute left-[30%] top-[30%] w-[40%] h-[2px]"
                  />
                  <div
                    style={{
                      borderColor: `${agent.color}88`,
                      backgroundColor: '#10141A'
                    }}
                    className="absolute left-[5%] top-[55%] w-[90%] h-[45%] border clip-armor"
                  />
                  <div
                    style={{ backgroundColor: agent.color }}
                    className="absolute left-[47%] top-[60%] w-[6%] h-[35%] opacity-50"
                  />
                </div>
              </div>
            )}

            {/* Neon Scanning Laser Line */}
            {liveMotion && (
              <div
                style={{
                  background: `linear-gradient(90deg, transparent, ${agent.color}, transparent)`,
                  animation: `${scanAnimClass} 3.5s linear infinite`
                }}
                className="absolute left-0 right-0 top-0 h-[1px] pointer-events-none"
              />
            )}
          </div>

          {/* Bottom Phase Tag Strip */}
          <div
            style={{
              borderTopColor: `${agent.color}33`,
              backgroundColor: isRunning ? `${agent.color}14` : 'rgba(255,255,255,0.02)'
            }}
            className="flex-shrink-0 border-t px-1.5 py-0.5 flex items-center justify-between font-mono-code text-[10px] tracking-wider"
          >
            <span style={{ color: agent.color }}>{agent.phase}</span>
            <span className="text-[#5C646E]">{agent.name[0]}</span>
          </div>
        </div>

        {/* Cyberpunk Corner Accent Brackets */}
        <div
          style={{ borderColor: agent.color }}
          className="absolute -left-[1px] -top-[1px] w-2 h-2 border-t border-l pointer-events-none"
        />
        <div
          style={{ borderColor: agent.color }}
          className="absolute -right-[1px] -bottom-[1px] w-2 h-2 border-b border-r pointer-events-none"
        />
      </div>
    </div>
  );
};
