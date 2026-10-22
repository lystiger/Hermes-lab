import React from 'react';
import { PageHeader } from '../components/PageHeader';
import { Link, useNavigate } from 'react-router-dom';
import { useConsoleStore } from '../stores/useConsoleStore';
import { prefersReducedMotion } from '../theme/motion';
import { useAgents, useSettings } from '../api/hooks';

export const SettingsRoute: React.FC = () => {
  const navigate = useNavigate();
  const {
    
    ambient3d,
    setAmbient3d,
  } = useConsoleStore();

  const { agents } = useAgents();
  const { settings, updatedAt } = useSettings();

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

            </div>
          </div>
        </div>

        {/* Right Column: Registered operators (live from GET /agents) */}
        <div className="flex-1 min-w-[340px] p-5 bg-lys-base">
          <div className="font-sans text-[11px] tracking-wider text-lys-faint mb-3.5">
            REGISTERED OPERATORS
          </div>
          <div className="flex flex-col gap-2.5">
            {agents.map((ag) => (
              <div
                key={ag.id}
                onClick={() => navigate(`/agents/${ag.id}`)}
                className="flex justify-between items-baseline gap-4 font-sans text-[12px] cursor-pointer hover:underline"
              >
                <span className="text-lys-primary">{ag.displayName}</span>
                <span className="text-lys-muted text-right break-words">
                  {ag.model}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <section aria-label="Projects" className="p-5 border-b border-lys-subtle">
        <div className="font-sans text-[11px] tracking-wider text-lys-faint mb-3">PROJECTS</div>
        <Link
          to="/design"
          className="inline-flex items-center gap-2 px-3 py-2 text-[12px] border border-lys-default text-lys-primary hover:bg-lys-surface-interactive transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          Unigreen design boards
        </Link>
        <p className="mt-2 text-[11px] text-lys-faint">Choose the design direction; the choice is recorded in LysStack for review.</p>
      </section>

      <div className="p-5 font-sans text-[11px] text-lys-faint leading-relaxed">
        Operators come from Hermes (GET /agents).
      </div>
    </div>
  );
};

export default SettingsRoute;
