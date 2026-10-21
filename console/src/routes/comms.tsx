import React, { useEffect, useRef, useState } from 'react';
import { orchestratorApi, OrchestratorConversation, OrchestratorConversationSummary, OrchestratorOptions } from '../api/orchestrator';
import { Card } from '../components/Card';
import { PageHeader } from '../components/PageHeader';

const DRAFT_NOTE = 'Saved to LysStack/drafts as Draft. Only you can mark a brief Ready.';

/** The chat: a scrolling transcript, a thinking note while the model answers, and a composer. */
export const CommsRoute: React.FC = () => {
  const [options, setOptions] = useState<OrchestratorOptions | null>(null);
  const [conversations, setConversations] = useState<OrchestratorConversationSummary[]>([]);
  const [selected, setSelected] = useState<OrchestratorConversation | null>(null);
  const [model, setModel] = useState('claude-sonnet-5-5');
  const [effort, setEffort] = useState('');
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const transcriptEnd = useRef<HTMLDivElement | null>(null);

  const claude = options?.providers.find((p) => p.id === 'claude');

  const refreshList = () =>
    orchestratorApi.listConversations().then(setConversations).catch((e: Error) => setError(e.message));

  useEffect(() => {
    orchestratorApi.options().then(setOptions).catch((e: Error) => setError(e.message));
    refreshList();
  }, []);

  // Keep the newest message in view.
  useEffect(() => {
    transcriptEnd.current?.scrollIntoView?.({ block: 'end' });
  }, [selected?.messages.length, busy]);

  const open = (id: string) => {
    setError(null);
    orchestratorApi.getConversation(id).then(setSelected).catch((e: Error) => setError(e.message));
  };

  const newChat = async (): Promise<OrchestratorConversation> => {
    const created = await orchestratorApi.createConversation(model, effort || null);
    setSelected(created);
    await refreshList();
    return created;
  };

  const send = async () => {
    const content = draft.trim();
    if (!content || busy) return;
    setBusy(true);
    setError(null);
    setDraft('');
    let chat: OrchestratorConversation | null = selected;
    try {
      chat = selected ?? (await newChat());
      // Show the human's message at once; the server keeps it even if the model call fails.
      setSelected({ ...chat, messages: [...chat.messages, { role: 'user', content, at: new Date().toISOString() }] });
      await orchestratorApi.sendMessage(chat.id, content);
      setSelected(await orchestratorApi.getConversation(chat.id));
      await refreshList();
    } catch (e) {
      setError((e as Error).message);
      if (chat) {
        const current = chat;
        setSelected(await orchestratorApi.getConversation(current.id).catch(() => current));
      }
    } finally {
      setBusy(false);
    }
  };

  const onComposerKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends; Shift+Enter starts a new line.
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void send();
    }
  };

  return (
    <>
      <PageHeader title="Comms" subtitle="Orchestrator chat · draft only" />
      <div className="grid grid-cols-1 md:grid-cols-[260px_1fr] gap-4 p-6 min-h-0">
        <Card as="section" label="Conversations" bodyClassName="p-3 flex flex-col gap-3">
          <div className="flex flex-col gap-2">
            <label className="text-[11px] uppercase tracking-wider text-lys-faint" htmlFor="comms-model">Model</label>
            <select id="comms-model" className="bg-lys-surface-1 text-lys-primary text-[13px] p-1 rounded"
              value={model} onChange={(e) => setModel(e.target.value)}>
              {(claude?.models ?? ['claude-sonnet-5-5']).map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
            <label className="text-[11px] uppercase tracking-wider text-lys-faint" htmlFor="comms-effort">Reasoning effort</label>
            <select id="comms-effort" className="bg-lys-surface-1 text-lys-primary text-[13px] p-1 rounded"
              value={effort} onChange={(e) => setEffort(e.target.value)}>
              <option value="">default</option>
              {(claude?.efforts ?? []).map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
            <button type="button" className="text-[13px] p-1 rounded border border-lys-subtle"
              onClick={() => { setError(null); void newChat().catch((e: Error) => setError(e.message)); }} disabled={busy}>
              New chat
            </button>
          </div>
          <ul className="flex flex-col gap-1">
            {conversations.map((c) => (
              <li key={c.id}>
                <button type="button" onClick={() => open(c.id)} aria-current={selected?.id === c.id ? 'true' : undefined}
                  className={`w-full text-left text-[13px] text-lys-primary truncate p-1 rounded hover:bg-lys-surface-1 ${selected?.id === c.id ? 'bg-lys-surface-1' : ''}`}>
                  {c.title} <span className="text-lys-faint">· {c.model}{c.effort ? ` · ${c.effort}` : ''}</span>
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <Card as="section" label="Chat" bodyClassName="flex flex-col h-[70vh] min-h-[420px]">
          <div className="flex items-center justify-between gap-2 px-4 py-2 border-b border-lys-subtle">
            <span className="text-[13px] text-lys-primary truncate">{selected ? selected.title : 'No chat open'}</span>
            {selected && (
              <span className="text-[11px] text-lys-faint whitespace-nowrap">
                {selected.model}{selected.effort ? ` · ${selected.effort}` : ''} · rules {selected.system_commit.slice(0, 12)}
              </span>
            )}
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-3 flex flex-col gap-3" role="log" aria-live="polite" aria-label="Transcript">
            {!selected && <div className="text-[13px] text-lys-muted">Type a message to start a chat with the orchestrator.</div>}
            {selected && selected.messages.length === 0 && (
              <div className="text-[13px] text-lys-muted">Ask the orchestrator to draft a brief. It can't start or merge anything.</div>
            )}
            {selected?.messages.map((m, i) => (
              <div key={i} className={`flex flex-col gap-1 max-w-[85%] ${m.role === 'user' ? 'self-end items-end' : 'self-start items-start'}`}>
                <span className="text-[10px] uppercase tracking-wider text-lys-faint">{m.role === 'user' ? 'You' : 'Orchestrator'}</span>
                <div className={`whitespace-pre-wrap text-[13px] text-lys-primary rounded px-3 py-2 ${m.role === 'user' ? 'bg-lys-surface-2' : 'bg-lys-surface-1'}`}>
                  {m.content}
                </div>
                {m.drafts && m.drafts.length > 0 && (
                  <div className="text-[12px] text-lys-muted">
                    Drafts: {m.drafts.join(', ')}. {DRAFT_NOTE}
                  </div>
                )}
              </div>
            ))}
            {busy && <div role="status" className="self-start text-[12px] text-lys-muted">Orchestrator is replying…</div>}
            <div ref={transcriptEnd} />
          </div>

          {error && <div role="alert" className="px-4 pb-2 text-[13px] text-lys-status-danger">{error}</div>}

          <form className="flex items-end gap-2 px-4 py-3 border-t border-lys-subtle" onSubmit={(e) => { e.preventDefault(); void send(); }}>
            <label htmlFor="comms-input" className="sr-only">Message</label>
            <textarea id="comms-input" rows={2} value={draft} onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onComposerKey} disabled={busy}
              placeholder="Message the orchestrator (Enter to send, Shift+Enter for a new line)"
              className="flex-1 resize-none bg-lys-surface-1 text-lys-primary text-[13px] p-2 rounded" />
            <button type="submit" disabled={busy || !draft.trim()}
              className="text-[13px] px-3 py-2 rounded border border-lys-subtle disabled:opacity-40">
              {busy ? 'Waiting…' : 'Send'}
            </button>
          </form>
        </Card>
      </div>
    </>
  );
};

export default CommsRoute;
