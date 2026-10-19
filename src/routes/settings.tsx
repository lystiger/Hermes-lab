import React from 'react';
import { PageHeader } from '../components/PageHeader';
import { Freshness } from '../components/DataStates';
import { useNavigate } from 'react-router-dom';
import { Link } from 'react-router-dom';
import { ExecutionBackendStrip } from '../features/execution/ExecutionBackendStrip';
import { useConsoleStore } from '../stores/useConsoleStore';
import { prefersReducedMotion } from '../theme/motion';
import { useAgents, useExecution, useSettings } from '../api/hooks';

export const SettingsRoute: React.FC = () => {
  const navigate = useNavigate();
  const {
    
    ambient3d,
    setAmbient3d,
    portraits,
    setPortraits
  } = useConsoleStore();

  const { agents } = useAgents();
  const { settings, updatedAt } = useSettings();
  const { view, snapshotStatus, snapshotLoadedAt } = useExecution();

  return (
    <div className="flex flex-col min-h-full select-none bg-lys-base">
      <PageHeader title="Settings" subtitle="Runtime and presentation" updatedAt={updatedAt} />
      {/* Top Split: Runtime vs Budget/Policy */}
      <div className="flex flex-col lg:flex-row items-stretch border-b border-lys-subtle">
        {/* Left Column: Runtime & Environment */}
        <div className="flex-1 min-w-[340px] border-b lg:border-b-0 lg:border-r border-lys-subtle p-5 bg-lys-base">
          <div className="font-sans text-[11px] tracking-wider text-lys-faint mb-3.5">
            RUNTIME &amp; ENVIRONMENT
          </div>
          <div className="flex flex-col gap-2.5">
            {settings.runtime.map((s, idx) => (
              <div key={idx} className="flex justify-between items-baseline font-sans text-[12px]">
                <span className="text-lys-muted">{s.label}</span>
                <span style={{ color: s.color || 'var(--lys-text-primary)' }}>{s.value}</span>
              </div>
            ))}
          </div>

          {/* Interactive UI Settings */}
          <div className="mt-6 pt-4 border-t border-lys-subtle">
            <div className="font-sans text-[11px] tracking-wider text-lys-faint mb-3">
              CLIENT RENDERING &amp; 3D MOTION
            </div>
            
            <div className="flex flex-col gap-3 font-sans text-[12px]">
              <div className="flex items-center justify-between text-lys-muted">
                <span>Motion</span>
                <span className="text-lys-primary">{prefersReducedMotion() ? 'reduced (system setting)' : 'full (system setting)'}</span>
              </div>

              <label className="flex items-center justify-between text-lys-muted cursor-pointer">
                <span>3D Ambient Rings &amp; Perspective</span>
                <input
                  type="checkbox"
                  checked={ambient3d}
                  onChange={(e) => setAmbient3d(e.target.checked)}
                  className="accent-lys-gold cursor-pointer"
                />
              </label>

              <div className="flex items-center justify-between text-lys-muted">
                <span>Portraits Rendering</span>
                <select
                  value={portraits}
                  onChange={(e) => setPortraits(e.target.value as any)}
                  className="bg-lys-surface-1 border border-lys-default font-sans text-[11px] text-lys-primary px-2 py-0.5 outline-none cursor-pointer"
                >
                  <option value="both">Both (WebP + Marks)</option>
                  <option value="slots">WebP Avatars Only</option>
                  <option value="marks">Cyber Sigils Only</option>
                </select>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Budget & Policy */}
        <div className="flex-1 min-w-[340px] p-5 bg-lys-base">
          <div className="font-sans text-[11px] tracking-wider text-lys-faint mb-3.5">
            BUDGET &amp; POLICY
          </div>
          <div className="flex flex-col gap-2.5">
            {settings.policy.map((s, idx) => (
              <div key={idx} className="flex justify-between items-baseline font-sans text-[12px]">
                <span className="text-lys-muted">{s.label}</span>
                <span style={{ color: s.color || 'var(--lys-text-primary)' }}>{s.value}</span>
              </div>
            ))}
          </div>

          {/* Registered Operators Summary */}
          <div className="mt-6 pt-4 border-t border-lys-subtle">
            <div className="font-sans text-[11px] tracking-wider text-lys-faint mb-3">
              REGISTERED OPERATORS
            </div>
            <div className="flex flex-col gap-1">
              {agents.map((ag) => {
                const accentColor = ag.presentation?.accentColor || 'var(--lys-text-muted)';
                return (
                  <div
                    key={ag.id}
                    onClick={() => navigate(`/agents/${ag.id}`)}
                    style={{ borderLeftColor: accentColor }}
                    className="flex items-center gap-3.5 p-2.5 bg-lys-surface-1 border-l-2 hover:bg-lys-surface-2 cursor-pointer transition-colors"
                  >
                    <span
                      style={{ borderColor: accentColor, backgroundColor: `color-mix(in srgb, ${accentColor} 13%, transparent)` }}
                      className="w-3.5 h-3.5 border clip-hex flex items-center justify-center font-sans text-[9px]"
                    >
                      {ag.displayName[0]}
                    </span>
                    <span className="w-20 text-[13px] text-lys-primary">{ag.displayName}</span>
                    <span style={{ color: accentColor }} className="w-16 font-sans text-[11px] tracking-wider font-semibold">
                      {ag.phase || 'IDLE'}
                    </span>
                    <span className="flex-1 min-w-0 font-sans text-[11px] text-lys-muted break-words">
                      {ag.model}
                    </span>
                    <span className="w-24 text-right font-sans text-[11px] text-lys-faint">
                      {ag.capabilities[0] || 'agent'}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Execution backends: live from GET /execution (replaces the static Herdr sandbox mock) */}
      <div className="p-5 border-b border-lys-subtle bg-lys-surface-0">
        <div className="flex items-center justify-between mb-3 font-sans text-[11px]">
          <span className="tracking-wider text-lys-faint">EXECUTION BACKENDS</span>
          <Link to="/execution" className="text-lys-gold hover:underline">open execution →</Link>
        </div>
        <div className="flex justify-end pb-2"><Freshness at={snapshotLoadedAt ? Date.parse(snapshotLoadedAt) : null} /></div>
        <ExecutionBackendStrip backends={view.backends} openrig={view.openrig} loaded={snapshotStatus === 'ready'} />
      </div>

      <div className="p-5 font-sans text-[11px] text-lys-faint leading-relaxed">
        Operators come from Hermes (GET /agents). Portraits resolve from <span className="text-lys-muted">public/agents/</span>.
      </div>
    </div>
  );
};

export default SettingsRoute;
