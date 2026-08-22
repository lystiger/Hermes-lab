import React, { useState } from 'react';
import { AgentPresentation, AgentStatus } from '../../api/types';
import { useConsoleStore } from '../../stores/useConsoleStore';

interface AgentPortraitProps {
  displayName: string;
  presentation?: AgentPresentation;
  status?: AgentStatus;
  phase?: string;
  crawlCode?: string;
  size?: 'sm' | 'md' | 'lg';
  showCode?: boolean;
}

export const AgentPortrait: React.FC<AgentPortraitProps> = ({
  displayName,
  presentation,
  status = 'IDLE',
  phase = 'IDLE',
  crawlCode = '',
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

  const accentColor = presentation?.accentColor || '#8C949F';
  const avatarUrl = presentation?.avatarUrl;
  const initial = displayName ? displayName.charAt(0).toUpperCase() : '?';
  const code = presentation?.code || displayName.slice(0, 4).toUpperCase();
  const isRunning = status === 'RUNNING';

  const hasAvatar = Boolean(avatarUrl) && !imgError;
  const showSlot = hasAvatar && (portraits === 'both' || portraits === 'slots');
  const showMark = !hasAvatar || portraits === 'marks' || (portraits === 'both' && !avatarUrl);

  const scanAnimClass = size === 'lg' ? 'lys-scan-tall' : size === 'md' ? 'lys-scan-mid' : 'lys-scan';
  
  const animProfile = presentation?.animationProfile || 'relaxed';
  const breatheAnim = !liveMotion ? 'none' :
    animProfile === 'quick' ? 'lys-breathe-quick 3.2s ease-in-out infinite' :
    animProfile === 'slow' ? 'lys-breathe-slow 11s ease-in-out infinite' :
    'lys-breathe 7s ease-in-out infinite';

  return (
    <div
      style={{ perspective: size === 'lg' ? '900px' : size === 'md' ? '640px' : '420px' }}
      className="flex-shrink-0 select-none"
    >
      <div
        style={{
          transformStyle: 'preserve-3d',
          animation: breatheAnim
        }}
        className={`relative ${dimClasses} transition-transform duration-300 hover:rotate-y-[-11deg] hover:rotate-x-[5deg] hover:translate-z-[10px]`}
      >
        <div
          style={{
            borderColor: isRunning ? `${accentColor}66` : '#1F242B',
            backgroundColor: '#0E1116'
          }}
          className="absolute inset-0 border overflow-hidden flex flex-col"
        >
          {/* Crawl Code Background */}
          {showCode && crawlCode && (
            <div className="absolute inset-0 opacity-[0.13] overflow-hidden pointer-events-none">
              <div
                style={{
                  color: accentColor,
                  animation: liveMotion ? 'lys-crawl 12s linear infinite' : 'none'
                }}
                className="font-mono-code text-[8px] leading-[10px] whitespace-pre"
              >
                {crawlCode + crawlCode}
              </div>
            </div>
          )}

          {/* WebP Image Portrait */}
          <div className="relative flex-1 min-h-0 overflow-hidden flex items-center justify-center bg-[#0C0E11]">
            {showSlot && avatarUrl ? (
              <img
                src={avatarUrl}
                alt={`${displayName} Portrait`}
                onError={() => setImgError(true)}
                className="w-full h-full object-cover select-none pointer-events-none"
              />
            ) : null}

            {/* Fallback Cybernetic Geometric Sigil / Initials Glyphs for un-portrayed or dynamic agents */}
            {showMark && (
              <div className="absolute inset-0 flex flex-col items-center justify-center pb-2 pointer-events-none">
                <div className="relative w-[54%] h-[68%] flex items-center justify-center">
                  <div
                    style={{
                      borderColor: accentColor,
                      backgroundColor: `${accentColor}20`
                    }}
                    className="absolute inset-0 border clip-hex flex items-center justify-center"
                  >
                    <span
                      style={{ color: accentColor }}
                      className="font-mono-code font-bold text-[18px] opacity-80"
                    >
                      {initial}
                    </span>
                  </div>
                  <div
                    style={{ backgroundColor: accentColor }}
                    className="absolute left-[20%] top-[30%] w-[60%] h-[2px] opacity-70"
                  />
                  <div
                    style={{
                      borderColor: `${accentColor}70`,
                      backgroundColor: '#10141A'
                    }}
                    className="absolute left-[10%] top-[55%] w-[80%] h-[40%] border clip-armor"
                  />
                </div>
                {code && (
                  <span
                    style={{ color: accentColor }}
                    className="font-mono-code text-[9px] tracking-wider mt-1 opacity-70"
                  >
                    {code}
                  </span>
                )}
              </div>
            )}

            {/* Neon Scanning Laser Line */}
            {liveMotion && (
              <div
                style={{
                  background: `linear-gradient(90deg, transparent, ${accentColor}, transparent)`,
                  animation: `${scanAnimClass} 3.5s linear infinite`
                }}
                className="absolute left-0 right-0 top-0 h-[1px] pointer-events-none"
              />
            )}
          </div>

          {/* Bottom Phase Tag Strip */}
          <div
            style={{
              borderTopColor: `${accentColor}33`,
              backgroundColor: isRunning ? `${accentColor}14` : 'rgba(255,255,255,0.02)'
            }}
            className="flex-shrink-0 border-t px-1.5 py-0.5 flex items-center justify-between font-mono-code text-[10px] tracking-wider"
          >
            <span style={{ color: accentColor }}>{phase}</span>
            <span className="text-[#5C646E]">{initial}</span>
          </div>
        </div>

        {/* Cyberpunk Corner Accent Brackets */}
        <div
          style={{ borderColor: accentColor }}
          className="absolute -left-[1px] -top-[1px] w-2 h-2 border-t border-l pointer-events-none"
        />
        <div
          style={{ borderColor: accentColor }}
          className="absolute -right-[1px] -bottom-[1px] w-2 h-2 border-b border-r pointer-events-none"
        />
      </div>
    </div>
  );
};
