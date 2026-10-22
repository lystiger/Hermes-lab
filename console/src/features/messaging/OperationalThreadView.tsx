import React, { useState, useMemo } from 'react';
import { Cog, CornerDownRight, Layers, X, GitCommit, FileText, ChartColumn, ClipboardList, List, type LucideIcon } from 'lucide-react';
import { useThreads, useMessages, useAgents } from '../../api/hooks';
import { resolveActorPresentation } from '../../api/actors';
import { hermesApi } from '../../api/client';
import { ArtifactRef, Message } from '../../api/types';
import { CyberButton } from '../../components/CyberButton';
import { formatTimeOfDay } from '../time/format';
import { ErrorState } from '../../components/DataStates';

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
  const { threads, error: threadsError } = useThreads(jobId);
  const activeThread = threads.find((t) => t.id === threadId || (jobId && (t.jobId === jobId || t.id.includes(jobId)))) || threads[0];
  const targetThreadId = threadId || activeThread?.id || (jobId ? `thread_job_${jobId}` : null);

  const { messages, loading: loadingMessages, error: messagesError, refetch } = useMessages(targetThreadId);
  const [sendError, setSendError] = useState<string | null>(null);
  const fetchError = messagesError || threadsError;
  const { agents } = useAgents();

  const [selectedConversationId, setSelectedConversationId] = useState<string>('all');
  const [selectedArtifact, setSelectedArtifact] = useState<ArtifactRef | null>(null);
  const [operatorText, setOperatorText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [targetRecipient, setTargetRecipient] = useState<string>(assignedAgentIds[0] || 'hermes');
  // The message being replied to. Its id, conversation and correlation travel with the send (F3).
  const [replyTarget, setReplyTarget] = useState<Message | null>(null);
  const replyToMessageId = replyTarget?.id ?? null;

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
    setSendError(null);
    try {
      // A reply carries replyTo; its conversation is inherited; correlation links back to the original message.
      await hermesApi.sendMessage(
        targetThreadId,
        operatorText.trim(),
        [targetRecipient],
        'operator',
        'operator_note',
        replyTarget?.conversationId ?? undefined,
        replyTarget?.id,
        replyTarget ? (replyTarget.correlationId ?? replyTarget.id) : undefined
      );
      setOperatorText('');
      // Cleared only once the send succeeded; a failed send keeps the text and the reply context.
      setReplyTarget(null);
      refetch();
    } catch (err) {
      // The typed text and the reply target are kept so the operator can retry.
      setSendError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsSending(false);
    }
  };

  const formatTime = (isoString?: string) => formatTimeOfDay(isoString);

  const getArtifactIcon = (type: string): LucideIcon => {
    switch (type) {
      case 'git_commit':
        return GitCommit;
      case 'handoff':
        return FileText;
      case 'test_report':
      case 'verification_report':
        return ChartColumn;
      case 'run_summary':
        return ClipboardList;
      case 'log':
        return List;
      default:
        return Layers;
    }
  };

  return (
    <div className="flex flex-col bg-lys-surface-0 border border-lys-subtle p-4 select-none">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2 font-sans text-[11px] text-lys-faint mb-3 pb-2 border-b border-lys-subtle">
        <div className="flex items-center gap-2">
          <span className="tracking-wider text-lys-primary font-semibold">
            OPERATIONAL THREAD &amp; HANDOFFS
          </span>
          <span className="text-lys-faint">· {targetThreadId || 'No active thread'}</span>
        </div>

        {/* Conversation Filter Selector */}
        {conversations.length > 0 && (
          <div className="flex items-center gap-1.5 text-[10px]">
            <span className="text-lys-faint">CONV:</span>
            <select
              value={selectedConversationId}
              onChange={(e) => setSelectedConversationId(e.target.value)}
              className="bg-lys-surface-1 border border-lys-default text-lys-primary px-1.5 py-0.5 outline-none cursor-pointer"
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

        <span className="text-lys-faint">GET /threads/{'{id}'}/messages</span>
      </div>

      {/* Messages Feed */}
      <div className="flex flex-col gap-3 min-h-[140px] max-h-[380px] overflow-y-auto pr-1">
        {loadingMessages && filteredMessages.length === 0 ? (
          <div className="py-6 text-center font-sans text-[11px] text-lys-faint">
            Loading operational messages...
          </div>
        ) : fetchError && messages.length === 0 ? (
          <ErrorState label="Operational messages" error={fetchError} onRetry={refetch} />
        ) : filteredMessages.length === 0 ? (
          <div className="py-6 text-center font-sans text-[11px] text-lys-faint">
            No operational messages or phase handoffs recorded for this job yet.
          </div>
        ) : (
          filteredMessages.map((msg: Message) => {
            const senderPres = resolveActorPresentation(msg.from.id, agents);
            const senderCol = msg.from.accentColor || senderPres.accentColor || 'var(--lys-accent-gold)';
            const isVerification = msg.kind === 'verification_result';
            const isWarning = msg.kind === 'warning';
            const isA2A = msg.kind === 'a2a' || ['review_request', 'correction_request', 'correction_result', 'question', 'answer'].includes(msg.intent || '');
            const isOperator = msg.kind === 'operator';

            return (
              <div
                key={msg.id}
                style={{
                  borderLeftColor: isWarning
                    ? 'var(--lys-status-danger)'
                    : isVerification
                    ? 'var(--lys-status-success)'
                    : isA2A
                    ? 'var(--lys-agent-gemini)'
                    : isOperator
                    ? 'var(--lys-text-primary)'
                    : senderCol
                }}
                className={`p-3 bg-lys-surface-1 border border-lys-subtle border-l-2 flex flex-col gap-1.5 transition-colors hover:border-lys-default ${
                  isA2A ? 'bg-lys-surface-1' : ''
                }`}
              >
                {/* Meta Header */}
                <div className="flex items-center justify-between flex-wrap gap-1 font-sans text-[11px]">
                  <div className="flex items-center flex-wrap gap-1.5">
                    {/* Avatar / Sigil */}
                    {(

                      <span
                        style={{ color: senderCol, borderColor: `color-mix(in srgb, ${senderCol} 27%, transparent)`, backgroundColor: `color-mix(in srgb, ${senderCol} 7%, transparent)` }}
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
                      <span className="text-[9.5px] text-lys-muted px-1 py-0.2 bg-lys-surface-2 border border-lys-default">
                        {senderPres.subtitle}
                      </span>
                    )}

                    {/* Recipient Arrow */}
                    {msg.to && msg.to.length > 0 && (
                      <>
                        <span className="text-lys-faint">→</span>
                        <span className="text-lys-muted">
                          {msg.to.map((t) => t.displayName).join(', ')}
                        </span>
                      </>
                    )}

                    {/* Tool Actor Indicator (Phase 7) */}
                    {msg.from.kind === 'tool' || msg.kind === 'tool_result' ? (
                      <span className="px-1 py-0.2 border border-lys-agent-gemini/40 bg-lys-agent-gemini/10 text-lys-info text-[9.5px] font-bold">
                        <Cog size={10} strokeWidth={2} aria-hidden="true" className="inline-block mr-1 -mt-px" /> TOOL
                      </span>
                    ) : null}

                    {/* Subagent Indicator (Phase 7) */}
                    {(msg.from.id.startsWith('subagent_') || msg.metadata?.subagent) && (
                      <span className="px-1 py-0.2 border border-lys-success/40 bg-lys-success/10 text-lys-agent-codex text-[9.5px] font-bold">
                        SUBAGENT {msg.metadata?.parentAgentId ? `(parent: ${msg.metadata.parentAgentId})` : ''}
                      </span>
                    )}

                    {/* Delegation Indicator & Task Info (Phase 7) */}
                    {(msg.kind === 'delegation' || msg.intent === 'task_request') && (
                      <span className="px-1 py-0.2 border border-lys-violet/40 bg-lys-violet/10 text-lys-violet text-[9.5px] font-bold">
                        DELEGATION {msg.metadata?.delegatedBy ? `· by ${msg.metadata.delegatedBy}` : ''}
                      </span>
                    )}

                    {/* Kind & Intent Chips */}
                    <span className="ml-1 text-[10px] text-lys-gold bg-lys-gold/8 px-1.5 py-0.2 border border-lys-gold/20">
                      {msg.kind.toUpperCase()} {msg.intent ? `· ${msg.intent}` : ''}
                    </span>

                    {/* Required Capabilities Badges (Phase 7) */}
                    {Array.isArray(msg.metadata?.requiredCapabilities) && msg.metadata.requiredCapabilities.length > 0 && (
                      <span className="flex items-center gap-1 text-[9px] text-lys-secondary bg-lys-surface-1 px-1.5 py-0.2 border border-lys-default">
                        req: {msg.metadata.requiredCapabilities.join(', ')}
                      </span>
                    )}

                    {/* Conversation Tag */}
                    {msg.conversationId && (
                      <span className="text-[9.5px] text-lys-agent-gemini bg-lys-agent-gemini/8 px-1.5 py-0.2 border border-lys-agent-gemini/20">
                        {msg.conversationId}
                      </span>
                    )}

                    {/* Reply-To Badge */}
                    {msg.replyTo && (
                      <span className="text-[9.5px] text-lys-muted bg-lys-surface-2 px-1.5 py-0.2 border border-lys-default">
                        <CornerDownRight size={10} strokeWidth={2} aria-hidden="true" className="inline-block mr-1 -mt-px" /> reply: {msg.replyTo}
                      </span>
                    )}

                    {/* Correlation ID */}
                    {msg.correlationId && (
                      <span className="text-[9.5px] text-lys-faint">
                        corr:{msg.correlationId}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-lys-faint">{formatTime(msg.createdAt)}</span>
                    <button
                      type="button"
                      onClick={() => {
                        setReplyTarget(msg);
                        if (msg.from.id !== 'operator') {
                          setTargetRecipient(msg.from.id);
                        }
                      }}
                      className="text-lys-faint hover:text-lys-gold text-[10px] cursor-pointer"
                      title="Reply to this message"
                    >
                      reply
                    </button>
                  </div>
                </div>

                {/* Message Operational Body */}
                <p className="text-[12px] text-lys-primary font-sans leading-relaxed whitespace-pre-wrap">
                  {msg.text}
                </p>

                {/* Artifact Chips */}
                {msg.artifactRefs && msg.artifactRefs.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-1 pt-1 border-t border-lys-subtle">
                    {msg.artifactRefs.map((art, idx) => (
                      <button
                        key={art.id || idx}
                        type="button"
                        onClick={() => setSelectedArtifact(art)}
                        className="flex items-center gap-1 px-2 py-0.5 bg-lys-surface-1 hover:bg-lys-surface-2 border border-lys-default hover:border-lys-gold text-lys-muted hover:text-lys-primary font-sans text-[10.5px] transition-colors cursor-pointer"
                      >
                        {(() => { const ArtIcon = getArtifactIcon(art.type); return <ArtIcon size={12} strokeWidth={2} aria-hidden="true" className="text-lys-gold" />; })()}
                        <span>{art.label || art.type}</span>
                        {art.type === 'git_commit' && (
                          <span className="text-lys-faint">{art.ref.slice(0, 7)}</span>
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
        <form onSubmit={handleSendOperatorMessage} className="mt-3 pt-3 border-t border-lys-subtle flex flex-col gap-2">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <span className="font-sans text-[10px] text-lys-faint">OPERATOR DISPATCH:</span>
              <select
                value={targetRecipient}
                onChange={(e) => setTargetRecipient(e.target.value)}
                className="bg-lys-surface-1 border border-lys-default font-sans text-[10.5px] text-lys-primary px-2 py-0.5 outline-none cursor-pointer"
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
              <div className="flex items-center gap-1 text-[10px] font-sans text-lys-gold">
                <span>Replying to {replyTarget?.id}{replyTarget?.text ? ` · "${replyTarget.text.slice(0, 40)}"` : ''}</span>
                <button
                  type="button"
                  onClick={() => setReplyTarget(null)}
                  aria-label="Cancel reply"
                  title="Cancel reply"
                  className="text-lys-faint hover:text-lys-danger ml-1 cursor-pointer"
                >
                  <X size={12} strokeWidth={2} aria-hidden="true" />
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
              className="flex-1 bg-lys-surface-1 border border-lys-default focus:border-lys-gold font-sans text-[11px] text-lys-primary px-3 py-1 outline-none transition-colors"
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
        {sendError && (
          <div role="alert" className="mt-2 font-sans text-[11px] text-lys-danger">
            Message not sent: {sendError}. Your text is kept.
          </div>
        )}

      {/* Artifact Inspection Modal */}
      {selectedArtifact && (
        <div
          style={{ backgroundColor: 'color-mix(in srgb, var(--lys-ink) 75%, transparent)' }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          onClick={() => setSelectedArtifact(null)}
        >
          <div
            className="bg-lys-surface-0 border border-lys-gold max-w-md w-full p-4 font-sans select-none shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-2 mb-3 border-b border-lys-subtle">
              <div className="flex items-center gap-2">
                <Layers size={14} strokeWidth={2} aria-hidden="true" className="text-lys-gold" />
                <span className="text-[12px] font-semibold text-lys-primary">
                  ARTIFACT METADATA INSPECTION
                </span>
              </div>
              <button
                type="button"
                onClick={() => setSelectedArtifact(null)}
                aria-label="Close artifact"
                title="Close artifact"
                className="text-lys-faint hover:text-lys-primary text-[14px] cursor-pointer"
              >
                <X size={14} strokeWidth={2} aria-hidden="true" />
              </button>
            </div>

            <div className="flex flex-col gap-2 text-[11px]">
              <div className="flex justify-between border-b border-lys-subtle pb-1">
                <span className="text-lys-faint">ID:</span>
                <span className="text-lys-primary">{selectedArtifact.id}</span>
              </div>
              <div className="flex justify-between border-b border-lys-subtle pb-1">
                <span className="text-lys-faint">Type:</span>
                <span className="text-lys-gold uppercase">{selectedArtifact.type}</span>
              </div>
              <div className="flex justify-between border-b border-lys-subtle pb-1">
                <span className="text-lys-faint">Label:</span>
                <span className="text-lys-primary">{selectedArtifact.label}</span>
              </div>
              <div className="flex flex-col gap-1 border-b border-lys-subtle pb-1">
                <span className="text-lys-faint">Reference:</span>
                <span className="text-lys-muted bg-lys-surface-1 p-1.5 text-[10.5px] break-all border border-lys-subtle">
                  {selectedArtifact.ref}
                </span>
              </div>
              <div className="flex justify-between items-center border-b border-lys-subtle pb-1.5 pt-0.5">
                <span className="text-lys-faint">Trust:</span>
                <div>
                  {selectedArtifact.trust?.status === "verified" && selectedArtifact.trust.kind === "path_containment" && (
                    <span className="text-[10px] text-lys-success bg-lys-success/8 border border-lys-success/27 px-1.5 py-0.5 font-semibold">
                      VERIFIED · PATH CONTAINED
                    </span>
                  )}
                  {(selectedArtifact.trust?.status === "not_applicable" || selectedArtifact.trust?.kind === "git_reference") && (
                    <span className="text-[10px] text-lys-gold bg-lys-gold/8 border border-lys-gold/27 px-1.5 py-0.5 font-semibold">
                      GIT REFERENCE
                    </span>
                  )}
                  {(!selectedArtifact.trust || selectedArtifact.trust.status === "unverified") && (
                    <span className="text-[10px] text-lys-danger bg-lys-danger/8 border border-lys-danger/27 px-1.5 py-0.5 font-semibold">
                      UNVERIFIED
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="mt-3 text-[10.5px] text-lys-muted text-right">
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
