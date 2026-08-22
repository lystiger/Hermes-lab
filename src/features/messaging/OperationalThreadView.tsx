import React, { useState } from 'react';
import { useThreads, useMessages, useAgents } from '../../api/hooks';
import { resolveActorPresentation } from '../../api/actors';
import { lysStackApi } from '../../api/client';
import { ArtifactRef, Message } from '../../api/types';
import { CyberButton } from '../../components/CyberButton';

interface OperationalThreadViewProps {
  jobId?: string;
  threadId?: string;
  assignedAgentIds?: string[];
}

export const OperationalThreadView: React.FC<OperationalThreadViewProps> = ({
  jobId,
  threadId,
  assignedAgentIds = []
}) => {
  const { threads } = useThreads(jobId);
  const activeThread = threads.find((t) => t.id === threadId || (jobId && (t.jobId === jobId || t.id.includes(jobId)))) || threads[0];
  const targetThreadId = threadId || activeThread?.id || (jobId ? `thread_job_${jobId}` : null);

  const { messages, loading: loadingMessages, refetch } = useMessages(targetThreadId);
  const { agents } = useAgents();

  const [selectedArtifact, setSelectedArtifact] = useState<ArtifactRef | null>(null);
  const [operatorText, setOperatorText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [targetRecipient, setTargetRecipient] = useState<string>(assignedAgentIds[0] || 'lysstack');

  const handleSendOperatorMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetThreadId || !operatorText.trim() || isSending) return;

    setIsSending(true);
    try {
      await lysStackApi.sendMessage(
        targetThreadId,
        operatorText.trim(),
        [targetRecipient],
        'operator',
        'operator_note'
      );
      setOperatorText('');
      refetch();
    } catch (err) {
      console.error('Failed to send operator message:', err);
    } finally {
      setIsSending(false);
    }
  };

  const formatTime = (isoString?: string) => {
    if (!isoString) return '—';
    try {
      const d = new Date(isoString);
      return d.toTimeString().slice(0, 8);
    } catch {
      return isoString.slice(11, 19) || isoString;
    }
  };

  const getArtifactIcon = (type: string) => {
    switch (type) {
      case 'git_commit':
        return '⎇';
      case 'handoff':
        return '🗎';
      case 'test_report':
      case 'verification_report':
        return '📊';
      case 'run_summary':
        return '📋';
      case 'log':
        return '≡';
      default:
        return '◈';
    }
  };

  return (
    <div className="flex flex-col bg-[#0C0E12] border border-[#1F242B] p-4 select-none">
      {/* Header */}
      <div className="flex items-center justify-between font-mono-code text-[11px] text-[#5C646E] mb-3 pb-2 border-b border-[#1A1E24]">
        <div className="flex items-center gap-2">
          <span className="tracking-wider text-[#E6E9ED] font-semibold">
            OPERATIONAL THREAD &amp; HANDOFFS
          </span>
          <span className="text-[#5C646E]">· {targetThreadId || 'No active thread'}</span>
        </div>
        <span className="flex items-center gap-1.5 text-[#3FB950]">
          <span className="w-1.5 h-1.5 rounded-full bg-[#3FB950] animate-pulse" />
          live substrate
        </span>
      </div>

      {/* Messages Feed */}
      <div className="flex flex-col gap-3 min-h-[140px] max-h-[360px] overflow-y-auto pr-1">
        {loadingMessages && messages.length === 0 ? (
          <div className="py-6 text-center font-mono-code text-[11px] text-[#5C646E]">
            Loading operational messages...
          </div>
        ) : messages.length === 0 ? (
          <div className="py-6 text-center font-mono-code text-[11px] text-[#5C646E]">
            No operational messages or phase handoffs recorded for this job yet.
          </div>
        ) : (
          messages.map((msg: Message) => {
            const senderPres = resolveActorPresentation(msg.from.id, agents);
            const senderCol = msg.from.accentColor || senderPres.accentColor || '#CBA35C';
            const isVerification = msg.kind === 'verification_result';
            const isWarning = msg.kind === 'warning';

            return (
              <div
                key={msg.id}
                style={{
                  borderLeftColor: isWarning ? '#F2555A' : isVerification ? '#3FB950' : senderCol
                }}
                className="p-3 bg-[#101318] border border-[#1A1E24] border-l-2 flex flex-col gap-1.5 transition-colors hover:border-[#2A3038]"
              >
                {/* Meta Header */}
                <div className="flex items-center justify-between flex-wrap gap-1 font-mono-code text-[11px]">
                  <div className="flex items-center gap-1.5">
                    {/* Sender Portrait/Badge */}
                    <span
                      style={{ color: senderCol, borderColor: `${senderCol}44`, backgroundColor: `${senderCol}11` }}
                      className="px-1.5 py-0.2 border font-semibold"
                    >
                      {msg.from.displayName}
                    </span>

                    {msg.to && msg.to.length > 0 && (
                      <>
                        <span className="text-[#5C646E]">→</span>
                        <span className="text-[#8C949F]">
                          {msg.to.map((t) => t.displayName).join(', ')}
                        </span>
                      </>
                    )}

                    {/* Kind & Intent Chips */}
                    <span className="ml-1 text-[10px] text-[#CBA35C] bg-[#CBA35C14] px-1.5 py-0.2 border border-[#CBA35C33]">
                      {msg.kind.toUpperCase()} {msg.intent ? `· ${msg.intent}` : ''}
                    </span>
                  </div>

                  <span className="text-[#5C646E]">{formatTime(msg.createdAt)}</span>
                </div>

                {/* Message Operational Body */}
                <p className="text-[12px] text-[#D7DCE2] font-mono-code leading-relaxed whitespace-pre-wrap">
                  {msg.text}
                </p>

                {/* Artifact Chips */}
                {msg.artifactRefs && msg.artifactRefs.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-1 pt-1 border-t border-[#161920]">
                    {msg.artifactRefs.map((art, idx) => (
                      <button
                        key={art.id || idx}
                        type="button"
                        onClick={() => setSelectedArtifact(art)}
                        className="flex items-center gap-1 px-2 py-0.5 bg-[#141820] hover:bg-[#1A202C] border border-[#242A36] hover:border-[#CBA35C] text-[#8C949F] hover:text-[#E6E9ED] font-mono-code text-[10.5px] transition-colors cursor-pointer"
                      >
                        <span className="text-[#CBA35C]">{getArtifactIcon(art.type)}</span>
                        <span>{art.label || art.type}</span>
                        {art.type === 'git_commit' && (
                          <span className="text-[#5C646E]">{art.ref.slice(0, 7)}</span>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Operator Send Action */}
      {targetThreadId && (
        <form onSubmit={handleSendOperatorMessage} className="mt-3 pt-3 border-t border-[#1A1E24] flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <span className="font-mono-code text-[10px] text-[#5C646E]">OPERATOR DISPATCH:</span>
            <select
              value={targetRecipient}
              onChange={(e) => setTargetRecipient(e.target.value)}
              className="bg-[#12151A] border border-[#242A36] font-mono-code text-[10.5px] text-[#E6E9ED] px-2 py-0.5 outline-none cursor-pointer"
            >
              <option value="lysstack">LysStack Control Plane</option>
              <option value="hermes_runner">Hermes Runner</option>
              {assignedAgentIds.map((aid) => (
                <option key={aid} value={aid}>
                  Agent: {aid.toUpperCase()}
                </option>
              ))}
            </select>
          </div>

          <div className="flex gap-2">
            <input
              type="text"
              value={operatorText}
              onChange={(e) => setOperatorText(e.target.value)}
              placeholder="Send operational guidance into job thread..."
              className="flex-1 bg-[#12151A] border border-[#242A36] focus:border-[#CBA35C] font-mono-code text-[11px] text-[#E6E9ED] px-3 py-1 outline-none transition-colors"
            />
            <CyberButton
              type="submit"
              variant="primary"
              size="sm"
              disabled={isSending || !operatorText.trim()}
            >
              {isSending ? 'SENDING...' : 'DISPATCH'}
            </CyberButton>
          </div>
        </form>
      )}

      {/* Artifact Inspection Modal */}
      {selectedArtifact && (
        <div
          style={{ backgroundColor: 'rgba(0,0,0,0.75)' }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          onClick={() => setSelectedArtifact(null)}
        >
          <div
            className="bg-[#0E1116] border border-[#CBA35C] max-w-md w-full p-4 font-mono-code select-none shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-2 mb-3 border-b border-[#1F242B]">
              <div className="flex items-center gap-2">
                <span className="text-[#CBA35C] text-[14px]">◈</span>
                <span className="text-[12px] font-semibold text-[#E6E9ED]">
                  ARTIFACT METADATA INSPECTION
                </span>
              </div>
              <button
                type="button"
                onClick={() => setSelectedArtifact(null)}
                className="text-[#5C646E] hover:text-[#E6E9ED] text-[14px] cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div className="flex flex-col gap-2 text-[11px]">
              <div className="flex justify-between border-b border-[#14171D] pb-1">
                <span className="text-[#5C646E]">ID:</span>
                <span className="text-[#E6E9ED]">{selectedArtifact.id}</span>
              </div>
              <div className="flex justify-between border-b border-[#14171D] pb-1">
                <span className="text-[#5C646E]">Type:</span>
                <span className="text-[#CBA35C] uppercase">{selectedArtifact.type}</span>
              </div>
              <div className="flex justify-between border-b border-[#14171D] pb-1">
                <span className="text-[#5C646E]">Label:</span>
                <span className="text-[#E6E9ED]">{selectedArtifact.label}</span>
              </div>
              <div className="flex flex-col gap-1 border-b border-[#14171D] pb-1">
                <span className="text-[#5C646E]">Reference:</span>
                <span className="text-[#8C949F] bg-[#12151A] p-1.5 text-[10.5px] break-all border border-[#1F242B]">
                  {selectedArtifact.ref}
                </span>
              </div>
              <div className="flex justify-between items-center border-b border-[#14171D] pb-1.5 pt-0.5">
                <span className="text-[#5C646E]">Trust:</span>
                <div>
                  {selectedArtifact.trust?.status === "verified" && selectedArtifact.trust.kind === "path_containment" && (
                    <span className="text-[10px] text-[#3FB950] bg-[#3FB95014] border border-[#3FB95044] px-1.5 py-0.5 font-semibold">
                      VERIFIED · PATH CONTAINED
                    </span>
                  )}
                  {(selectedArtifact.trust?.status === "not_applicable" || selectedArtifact.trust?.kind === "git_reference") && (
                    <span className="text-[10px] text-[#CBA35C] bg-[#CBA35C14] border border-[#CBA35C44] px-1.5 py-0.5 font-semibold">
                      GIT REFERENCE
                    </span>
                  )}
                  {(!selectedArtifact.trust || selectedArtifact.trust.status === "unverified") && (
                    <span className="text-[10px] text-[#F2555A] bg-[#F2555A14] border border-[#F2555A44] px-1.5 py-0.5 font-semibold">
                      UNVERIFIED
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="mt-3 text-[10.5px] text-[#8C949F] text-right">
              {selectedArtifact.trust?.status === "verified" && selectedArtifact.trust.kind === "path_containment"
                ? `Verified runtime artifact · ${selectedArtifact.trust.detail || "Contained within Hermes run root"}`
                : selectedArtifact.trust?.status === "not_applicable" || selectedArtifact.trust?.kind === "git_reference"
                ? "Git commit reference"
                : selectedArtifact.trust?.detail || "Runtime artifact reference · Verification unavailable"}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
