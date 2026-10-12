import React, { useState, useMemo } from 'react';
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

  const [selectedConversationId, setSelectedConversationId] = useState<string>('all');
  const [selectedArtifact, setSelectedArtifact] = useState<ArtifactRef | null>(null);
  const [operatorText, setOperatorText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [targetRecipient, setTargetRecipient] = useState<string>(assignedAgentIds[0] || 'hermes');
  const [replyToMessageId, setReplyToMessageId] = useState<string | null>(null);

  // Extract distinct conversation IDs present in the messages
  const conversations = useMemo(() => {
    const set = new Set<string>();
    messages.forEach((m) => {
      if (m.conversationId) set.add(m.conversationId);
    });
    return Array.from(set);
  }, [messages]);

  const filteredMessages = useMemo(() => {
    if (selectedConversationId === 'all') return messages;
    return messages.filter((m) => m.conversationId === selectedConversationId);
  }, [messages, selectedConversationId]);

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
      setReplyToMessageId(null);
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
      <div className="flex items-center justify-between flex-wrap gap-2 font-mono-code text-[11px] text-[#5C646E] mb-3 pb-2 border-b border-[#1A1E24]">
        <div className="flex items-center gap-2">
          <span className="tracking-wider text-[#E6E9ED] font-semibold">
            OPERATIONAL THREAD &amp; HANDOFFS
          </span>
          <span className="text-[#5C646E]">· {targetThreadId || 'No active thread'}</span>
        </div>

        {/* Conversation Filter Selector */}
        {conversations.length > 0 && (
          <div className="flex items-center gap-1.5 text-[10px]">
            <span className="text-[#5C646E]">CONV:</span>
            <select
              value={selectedConversationId}
              onChange={(e) => setSelectedConversationId(e.target.value)}
              className="bg-[#12151A] border border-[#242A36] text-[#E6E9ED] px-1.5 py-0.5 outline-none cursor-pointer"
            >
              <option value="all">All Messages ({messages.length})</option>
              {conversations.map((cid) => (
                <option key={cid} value={cid}>
                  {cid}
                </option>
              ))}
            </select>
          </div>
        )}

        <span className="flex items-center gap-1.5 text-[#3FB950]">
          <span className="w-1.5 h-1.5 rounded-full bg-[#3FB950] animate-pulse" />
          live substrate
        </span>
      </div>

      {/* Messages Feed */}
      <div className="flex flex-col gap-3 min-h-[140px] max-h-[380px] overflow-y-auto pr-1">
        {loadingMessages && filteredMessages.length === 0 ? (
          <div className="py-6 text-center font-mono-code text-[11px] text-[#5C646E]">
            Loading operational messages...
          </div>
        ) : filteredMessages.length === 0 ? (
          <div className="py-6 text-center font-mono-code text-[11px] text-[#5C646E]">
            No operational messages or phase handoffs recorded for this job yet.
          </div>
        ) : (
          filteredMessages.map((msg: Message) => {
            const senderPres = resolveActorPresentation(msg.from.id, agents);
            const senderCol = msg.from.accentColor || senderPres.accentColor || '#CBA35C';
            const isVerification = msg.kind === 'verification_result';
            const isWarning = msg.kind === 'warning';
            const isA2A = msg.kind === 'a2a' || ['review_request', 'correction_request', 'correction_result', 'question', 'answer'].includes(msg.intent || '');
            const isOperator = msg.kind === 'operator';

            return (
              <div
                key={msg.id}
                style={{
                  borderLeftColor: isWarning
                    ? '#F2555A'
                    : isVerification
                    ? '#3FB950'
                    : isA2A
                    ? '#5B8CFF'
                    : isOperator
                    ? '#E6E9ED'
                    : senderCol
                }}
                className={`p-3 bg-[#101318] border border-[#1A1E24] border-l-2 flex flex-col gap-1.5 transition-colors hover:border-[#2A3038] ${
                  isA2A ? 'bg-[#10141D]' : ''
                }`}
              >
                {/* Meta Header */}
                <div className="flex items-center justify-between flex-wrap gap-1 font-mono-code text-[11px]">
                  <div className="flex items-center flex-wrap gap-1.5">
                    {/* Avatar / Sigil */}
                    {senderPres.avatarUrl ? (
                      <img
                        src={senderPres.avatarUrl}
                        alt={msg.from.displayName}
                        className="w-4 h-4 rounded-full object-cover border border-[#242A36]"
                        onError={(e) => {
                          // Fallback to text sigil if image fails
                          (e.target as HTMLElement).style.display = 'none';
                        }}
                      />
                    ) : (
                      <span
                        style={{ color: senderCol, borderColor: `${senderCol}44`, backgroundColor: `${senderCol}11` }}
                        className="px-1 py-0.2 border text-[10px] font-bold"
                      >
                        {msg.from.displayName.charAt(0).toUpperCase()}
                      </span>
                    )}

                    {/* Sender Name */}
                    <span
                      style={{ color: senderCol }}
                      className="font-semibold"
                    >
                      {msg.from.displayName}
                    </span>

                    {/* Persona Subtitle */}
                    {senderPres.subtitle && (
                      <span className="text-[9.5px] text-[#8C949F] px-1 py-0.2 bg-[#161B22] border border-[#242A36]">
                        {senderPres.subtitle}
                      </span>
                    )}

                    {/* Recipient Arrow */}
                    {msg.to && msg.to.length > 0 && (
                      <>
                        <span className="text-[#5C646E]">→</span>
                        <span className="text-[#8C949F]">
                          {msg.to.map((t) => t.displayName).join(', ')}
                        </span>
                      </>
                    )}

                    {/* Tool Actor Indicator (Phase 7) */}
                    {msg.from.kind === 'tool' || msg.kind === 'tool_result' ? (
                      <span className="px-1 py-0.2 border border-[#388BFD66] bg-[#388BFD1A] text-[#79C0FF] text-[9.5px] font-bold">
                        ⚙ TOOL
                      </span>
                    ) : null}

                    {/* Subagent Indicator (Phase 7) */}
                    {(msg.from.id.startsWith('subagent_') || msg.metadata?.subagent) && (
                      <span className="px-1 py-0.2 border border-[#2EA04366] bg-[#2EA0431A] text-[#7EE787] text-[9.5px] font-bold">
                        SUBAGENT {msg.metadata?.parentAgentId ? `(parent: ${msg.metadata.parentAgentId})` : ''}
                      </span>
                    )}

                    {/* Delegation Indicator & Task Info (Phase 7) */}
                    {(msg.kind === 'delegation' || msg.intent === 'task_request') && (
                      <span className="px-1 py-0.2 border border-[#A371F766] bg-[#A371F71A] text-[#D2A8FF] text-[9.5px] font-bold">
                        DELEGATION {msg.metadata?.delegatedBy ? `· by ${msg.metadata.delegatedBy}` : ''}
                      </span>
                    )}

                    {/* Kind & Intent Chips */}
                    <span className="ml-1 text-[10px] text-[#CBA35C] bg-[#CBA35C14] px-1.5 py-0.2 border border-[#CBA35C33]">
                      {msg.kind.toUpperCase()} {msg.intent ? `· ${msg.intent}` : ''}
                    </span>

                    {/* Required Capabilities Badges (Phase 7) */}
                    {Array.isArray(msg.metadata?.requiredCapabilities) && msg.metadata.requiredCapabilities.length > 0 && (
                      <span className="flex items-center gap-1 text-[9px] text-[#A5D6FF] bg-[#141820] px-1.5 py-0.2 border border-[#242A36]">
                        req: {msg.metadata.requiredCapabilities.join(', ')}
                      </span>
                    )}

                    {/* Conversation Tag */}
                    {msg.conversationId && (
                      <span className="text-[9.5px] text-[#5B8CFF] bg-[#5B8CFF14] px-1.5 py-0.2 border border-[#5B8CFF33]">
                        {msg.conversationId}
                      </span>
                    )}

                    {/* Reply-To Badge */}
                    {msg.replyTo && (
                      <span className="text-[9.5px] text-[#8C949F] bg-[#161B22] px-1.5 py-0.2 border border-[#242A36]">
                        ↳ reply: {msg.replyTo}
                      </span>
                    )}

                    {/* Correlation ID */}
                    {msg.correlationId && (
                      <span className="text-[9.5px] text-[#5C646E]">
                        corr:{msg.correlationId}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-[#5C646E]">{formatTime(msg.createdAt)}</span>
                    <button
                      type="button"
                      onClick={() => {
                        setReplyToMessageId(msg.id);
                        if (msg.from.id !== 'operator') {
                          setTargetRecipient(msg.from.id);
                        }
                      }}
                      className="text-[#5C646E] hover:text-[#CBA35C] text-[10px] cursor-pointer"
                      title="Reply to this message"
                    >
                      reply
                    </button>
                  </div>
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
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <span className="font-mono-code text-[10px] text-[#5C646E]">OPERATOR DISPATCH:</span>
              <select
                value={targetRecipient}
                onChange={(e) => setTargetRecipient(e.target.value)}
                className="bg-[#12151A] border border-[#242A36] font-mono-code text-[10.5px] text-[#E6E9ED] px-2 py-0.5 outline-none cursor-pointer"
              >
                <option value="hermes">Hermes Runtime</option>
                <option value="hermes_runner">Hermes Runner</option>
                {assignedAgentIds.map((aid) => (
                  <option key={aid} value={aid}>
                    Agent: {aid.toUpperCase()}
                  </option>
                ))}
              </select>
            </div>

            {replyToMessageId && (
              <div className="flex items-center gap-1 text-[10px] font-mono-code text-[#CBA35C]">
                <span>Replying to {replyToMessageId}</span>
                <button
                  type="button"
                  onClick={() => setReplyToMessageId(null)}
                  className="text-[#5C646E] hover:text-[#F2555A] ml-1 cursor-pointer"
                >
                  ✕
                </button>
              </div>
            )}
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
