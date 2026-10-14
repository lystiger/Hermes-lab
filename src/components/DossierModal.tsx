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
  const accentColor = activeDossierAgent.presentation.accentColor || 'var(--lys-text-muted)';

  return (
    <div
      onClick={() => setActiveDossierAgent(null)}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-lys-base/85 backdrop-blur-md select-none lys-drawer"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ borderColor: `color-mix(in srgb, ${accentColor} 40%, transparent)` }}
        className="relative max-w-lg w-full max-h-[92vh] bg-lys-base border shadow-2xl flex flex-col overflow-hidden"
      >
        {/* Top Header */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-lys-surface-0 border-b border-lys-subtle">
          <div className="font-sans text-[12px] flex items-center gap-2">
            <span style={{ color: accentColor }}>[ OPERATIVE DOSSIER ]</span>
            <span className="text-lys-muted">·</span>
            <span className="text-lys-primary font-semibold">{activeDossierAgent.displayName}</span>
          </div>
          <button
            onClick={() => setActiveDossierAgent(null)}
            className="font-sans text-[12px] text-lys-muted hover:text-lys-primary px-2 py-0.5 border border-transparent hover:border-lys-default cursor-pointer transition-colors"
          >
            ✕ CLOSE
          </button>
        </div>

        {/* Character Card Image */}
        <div className="flex-1 overflow-y-auto p-4 flex items-center justify-center bg-lys-base">
          <img
            src={cardUrl}
            alt={`${activeDossierAgent.displayName} Character Card`}
            className="w-full max-h-[78vh] object-contain border border-lys-subtle shadow-lg"
          />
        </div>

        {/* Footer Meta */}
        <div className="px-4 py-2 bg-lys-surface-0 border-t border-lys-subtle flex items-center justify-between font-sans text-[11px] text-lys-faint">
          <span>{activeDossierAgent.model} · {activeDossierAgent.provider}</span>
          <span style={{ color: accentColor }}>{activeDossierAgent.role}</span>
        </div>
      </div>
    </div>
  );
};
