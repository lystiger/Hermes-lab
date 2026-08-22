import React from 'react';
import { useNavigate } from 'react-router-dom';
import { SandboxStatus } from '../features/tools/SandboxStatus';
import { useConsoleStore } from '../stores/useConsoleStore';

export const SettingsRoute: React.FC = () => {
  const navigate = useNavigate();
  const {
    runtimeSettings,
    policySettings,
    agents,
    liveMotion,
    setLiveMotion,
    ambient3d,
    setAmbient3d,
    portraits,
    setPortraits
  } = useConsoleStore();

  return (
    <div className="flex flex-col select-none bg-[#0A0B0D]">
      {/* Top Split: Runtime vs Budget/Policy */}
      <div className="flex flex-col lg:flex-row items-stretch border-b border-[#1F242B]">
        {/* Left Column: Runtime & Environment */}
        <div className="flex-1 min-w-[340px] border-b lg:border-b-0 lg:border-r border-[#1F242B] p-5 bg-[#0A0B0D]">
          <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-3.5">
            RUNTIME &amp; ENVIRONMENT
          </div>
          <div className="flex flex-col gap-2.5">
            {runtimeSettings.map((s, idx) => (
              <div key={idx} className="flex justify-between items-baseline font-mono-code text-[12px]">
                <span className="text-[#8C949F]">{s.label}</span>
                <span style={{ color: s.color || '#E6E9ED' }}>{s.value}</span>
              </div>
            ))}
          </div>

          {/* Interactive UI Settings */}
          <div className="mt-6 pt-4 border-t border-[#1F242B]">
            <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-3">
              CLIENT RENDERING &amp; 3D MOTION
            </div>
            
            <div className="flex flex-col gap-3 font-mono-code text-[12px]">
              <label className="flex items-center justify-between text-[#8C949F] cursor-pointer">
                <span>Live Motion &amp; Pulse FX</span>
                <input
                  type="checkbox"
                  checked={liveMotion}
                  onChange={(e) => setLiveMotion(e.target.checked)}
                  className="accent-[#CBA35C] cursor-pointer"
                />
              </label>

              <label className="flex items-center justify-between text-[#8C949F] cursor-pointer">
                <span>3D Ambient Rings &amp; Perspective</span>
                <input
                  type="checkbox"
                  checked={ambient3d}
                  onChange={(e) => setAmbient3d(e.target.checked)}
                  className="accent-[#CBA35C] cursor-pointer"
                />
              </label>

              <div className="flex items-center justify-between text-[#8C949F]">
                <span>Portraits Rendering</span>
                <select
                  value={portraits}
                  onChange={(e) => setPortraits(e.target.value as any)}
                  className="bg-[#12151A] border border-[#2A3038] font-mono-code text-[11px] text-[#E6E9ED] px-2 py-0.5 outline-none cursor-pointer"
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
        <div className="flex-1 min-w-[340px] p-5 bg-[#0A0B0D]">
          <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-3.5">
            BUDGET &amp; POLICY
          </div>
          <div className="flex flex-col gap-2.5">
            {policySettings.map((s, idx) => (
              <div key={idx} className="flex justify-between items-baseline font-mono-code text-[12px]">
                <span className="text-[#8C949F]">{s.label}</span>
                <span style={{ color: s.color || '#E6E9ED' }}>{s.value}</span>
              </div>
            ))}
          </div>

          {/* Registered Operators Summary */}
          <div className="mt-6 pt-4 border-t border-[#1F242B]">
            <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-3">
              REGISTERED OPERATORS
            </div>
            <div className="flex flex-col gap-1">
              {agents.map((ag) => (
                <div
                  key={ag.id}
                  onClick={() => navigate(`/agents/${ag.id}`)}
                  style={{ borderLeftColor: ag.color }}
                  className="flex items-center gap-3.5 p-2.5 bg-[#101216] border-l-2 hover:bg-[#161A20] cursor-pointer transition-colors"
                >
                  <span
                    style={{ borderColor: ag.color, backgroundColor: `${ag.color}22` }}
                    className="w-3.5 h-3.5 border clip-hex"
                  />
                  <span className="w-20 text-[13px] text-[#E6E9ED]">{ag.name}</span>
                  <span style={{ color: ag.color }} className="w-16 font-mono-code text-[11px] tracking-wider font-semibold">
                    {ag.phase}
                  </span>
                  <span className="flex-1 min-w-0 font-mono-code text-[11px] text-[#8C949F] truncate">
                    {ag.model}
                  </span>
                  <span className="w-24 text-right font-mono-code text-[11px] text-[#5C646E]">
                    max 1 job
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Herdr Container Runtime Sandbox Status */}
      <div className="p-5 border-b border-[#1F242B] bg-[#0C0E11]">
        <SandboxStatus />
      </div>

      <div className="p-5 font-mono-code text-[11px] text-[#5C646E] leading-relaxed">
        Configuration is synchronized with <span className="text-[#8C949F]">~/.lyscontrol/config.toml</span> and <span className="text-[#8C949F]">~/.lyscontrol/agents.toml</span>. Portraits resolve from <span className="text-[#8C949F]">public/agents/</span>.
      </div>
    </div>
  );
};

export default SettingsRoute;
