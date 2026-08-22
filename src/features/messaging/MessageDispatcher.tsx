import React, { useState } from 'react';
import { LysControlApi } from '../../api/client';
import { CyberButton } from '../../components/CyberButton';
import { useConsoleStore } from '../../stores/useConsoleStore';

export const MessageDispatcher: React.FC = () => {
  const { agents } = useConsoleStore();
  const [selectedAgent, setSelectedAgent] = useState('Hermes');
  const [prompt, setPrompt] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [lastResponse, setLastResponse] = useState<string | null>(null);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || isSending) return;

    setIsSending(true);
    setLastResponse(null);

    try {
      const res = await LysControlApi.dispatchAgentMessage(selectedAgent, prompt);
      setLastResponse(res.response);
      setPrompt('');
    } catch (err) {
      setLastResponse(`Error dispatching message: ${err}`);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="p-4 bg-[#0E1116] border border-[#1F242B] select-none">
      <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-2.5 flex items-center justify-between">
        <span>TACTICAL DISPATCH / AGENT COMMAND</span>
        <span className="text-[#CBA35C]">mesh://local</span>
      </div>

      <form onSubmit={handleSend} className="flex flex-col gap-2.5">
        <div className="flex items-center gap-2">
          <label className="font-mono-code text-[11px] text-[#8C949F]">Target:</label>
          <select
            value={selectedAgent}
            onChange={(e) => setSelectedAgent(e.target.value)}
            className="bg-[#12151A] border border-[#2A3038] font-mono-code text-[11px] text-[#E6E9ED] px-2 py-1 outline-none cursor-pointer"
          >
            <option value="Hermes">Hermes (Orchestrator)</option>
            {agents.map((ag) => (
              <option key={ag.id} value={ag.name}>
                {ag.name} ({ag.role.split('·')[0].trim()})
              </option>
            ))}
          </select>
        </div>

        <div className="flex gap-2">
          <input
            type="text"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Type command or prompt (e.g. /retry #142, /audit-tokens)..."
            className="flex-1 bg-[#12151A] border border-[#2A3038] focus:border-[#CBA35C] font-mono-code text-[12px] text-[#E6E9ED] px-3 py-1.5 outline-none transition-colors"
          />
          <CyberButton type="submit" variant="primary" size="md" disabled={isSending || !prompt.trim()}>
            {isSending ? 'SENDING...' : 'DISPATCH'}
          </CyberButton>
        </div>
      </form>

      {lastResponse && (
        <div className="mt-2.5 p-2 bg-[#14171C] border-l-2 border-[#CBA35C] font-mono-code text-[11px] text-[#D7DCE2]">
          {lastResponse}
        </div>
      )}
    </div>
  );
};
