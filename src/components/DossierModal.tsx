import React from 'react';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useEscape } from './keyboard';

export const DossierModal: React.FC = () => {
  const { activeDossierAgent, setActiveDossierAgent } = useConsoleStore();
  useEscape(() => setActiveDossierAgent(null), activeDossierAgent !== null);

  if (!activeDossierAgent || !activeDossierAgent.presentation?.characterCardUrl) {
    return null;
  }

  const cardUrl = activeDossierAgent.presentation.characterCardUrl;
  const accentColor = activeDossierAgent.presentation.accentColor || '#8C949F';

  return (
    <div
      onClick={() => setActiveDossierAgent(null)}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-[rgba(10,11,13,0.85)] backdrop-blur-md select-none animate-fade-in"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ borderColor: `${accentColor}66` }}
        className="relative max-w-lg w-full max-h-[92vh] bg-[#0A0B0D] border shadow-2xl flex flex-col overflow-hidden"
      >
        {/* Top Header */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-[#0C0E11] border-b border-[#1F242B]">
          <div className="font-mono-code text-[12px] flex items-center gap-2">
            <span style={{ color: accentColor }}>[ OPERATIVE DOSSIER ]</span>
            <span className="text-[#8C949F]">·</span>
            <span className="text-[#E6E9ED] font-semibold">{activeDossierAgent.displayName}</span>
          </div>
          <button
            onClick={() => setActiveDossierAgent(null)}
            className="font-mono-code text-[12px] text-[#8C949F] hover:text-[#E6E9ED] px-2 py-0.5 border border-transparent hover:border-[#2A3038] cursor-pointer transition-colors"
          >
            ✕ CLOSE
          </button>
        </div>

        {/* Character Card Image */}
        <div className="flex-1 overflow-y-auto p-4 flex items-center justify-center bg-[#07080A]">
          <img
            src={cardUrl}
            alt={`${activeDossierAgent.displayName} Character Card`}
            className="w-full max-h-[78vh] object-contain border border-[#1A1E24] shadow-lg"
          />
        </div>

        {/* Footer Meta */}
        <div className="px-4 py-2 bg-[#0C0E11] border-t border-[#1F242B] flex items-center justify-between font-mono-code text-[11px] text-[#5C646E]">
          <span>{activeDossierAgent.model} · {activeDossierAgent.provider}</span>
          <span style={{ color: accentColor }}>{activeDossierAgent.role}</span>
        </div>
      </div>
    </div>
  );
};
