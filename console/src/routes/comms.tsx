import React, { useEffect, useState } from 'react';
import { orchestratorApi, OrchestratorConversation, OrchestratorConversationSummary, OrchestratorOptions } from '../api/orchestrator';
import { ChatSidebar } from '../features/comms/ChatSidebar';
import { ChatThread } from '../features/comms/ChatThread';
import { Composer } from '../features/comms/Composer';

const DEFAULT_MODEL = 'claude-sonnet-5-5';

/**
 * Comms: a chat with the orchestrator, laid out like a chat app. The list is on the left, the open
 * chat is in the middle with its model and effort on top, and the composer is at the bottom.
 */
export const CommsRoute: React.FC = () => {
  const [options, setOptions] = useState<OrchestratorOptions | null>(null);
  const [conversations, setConversations] = useState<OrchestratorConversationSummary[]>([]);
  const [selected, setSelected] = useState<OrchestratorConversation | null>(null);
  // Used for the next chat when none is open. An open chat keeps its own model and effort.
  const [model, setModel] = useState(DEFAULT_MODEL);
  const [effort, setEffort] = useState('');
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const claude = options?.providers.find((p) => p.id === 'claude');
  const models = claude?.models ?? [DEFAULT_MODEL];
  const efforts = claude?.efforts ?? [];
  const shownModel = selected?.model ?? model;
  const shownEffort = selected ? selected.effort ?? '' : effort;

  const refreshList = () =>
    orchestratorApi.listConversations().then(setConversations).catch((e: Error) => setError(e.message));

  useEffect(() => {
    orchestratorApi.options().then(setOptions).catch((e: Error) => setError(e.message));
    void refreshList();
  }, []);

  const open = (id: string) => {
    setError(null);
    orchestratorApi.getConversation(id).then(setSelected).catch((e: Error) => setError(e.message));
  };

  const newChat = () => {
    setError(null);
    setSelected(null);
    setDraft('');
  };

  const send = async () => {
    const content = draft.trim();
    if (!content || busy) return;
    setBusy(true);
    setError(null);
    setDraft('');
    let chat: OrchestratorConversation | null = selected;
    try {
      chat = selected ?? (await orchestratorApi.createConversation(model, effort || null));
      const started = chat;
      // Show the human's message at once; the server keeps it even if the model call fails.
      setSelected({ ...started, messages: [...started.messages, { role: 'user', content, at: new Date().toISOString() }] });
      await orchestratorApi.sendMessage(started.id, content);
      setSelected(await orchestratorApi.getConversation(started.id));
      await refreshList();
    } catch (e) {
      setError((e as Error).message);
      if (chat) {
        const current = chat;
        setSelected(await orchestratorApi.getConversation(current.id).catch(() => current));
        await refreshList();
      }
    } finally {
      setBusy(false);
    }
  };

  const changeModel = async (next: string) => {
    if (!selected) return setModel(next);
    setError(null);
    try {
      await orchestratorApi.updateConversation(selected.id, { model: next });
      setSelected({ ...selected, model: next });
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const changeEffort = async (next: string) => {
    if (!selected) return setEffort(next);
    setError(null);
    try {
      await orchestratorApi.updateConversation(selected.id, { effort: next || null });
      setSelected({ ...selected, effort: next || null });
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const rename = async (id: string, title: string) => {
    setError(null);
    try {
      await orchestratorApi.updateConversation(id, { title });
      if (selected?.id === id) setSelected({ ...selected, title });
      await refreshList();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const remove = async (id: string) => {
    setError(null);
    try {
      await orchestratorApi.deleteConversation(id);
      if (selected?.id === id) setSelected(null);
      await refreshList();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="flex h-[calc(100vh-6rem)] min-h-[520px] overflow-hidden rounded-lg border border-lys-subtle bg-lys-surface-0">
      <aside className="hidden w-64 shrink-0 flex-col gap-2 border-r border-lys-subtle bg-lys-surface-1 p-2 md:flex">
        <ChatSidebar
          conversations={conversations}
          selectedId={selected?.id ?? null}
          onSelect={open}
          onNew={newChat}
          onRename={rename}
          onDelete={remove}
        />
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-lys-subtle px-4 py-2">
          <span className="truncate text-[13px] text-lys-primary">{selected ? selected.title : 'New chat'}</span>
          <div className="flex items-center gap-2">
            <label className="sr-only" htmlFor="comms-model">Model</label>
            <select id="comms-model" value={shownModel} onChange={(e) => void changeModel(e.target.value)}
              className="rounded bg-lys-surface-1 p-1 text-[12px] text-lys-primary">
              {models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
            <label className="sr-only" htmlFor="comms-effort">Reasoning effort</label>
            <select id="comms-effort" value={shownEffort} onChange={(e) => void changeEffort(e.target.value)}
              className="rounded bg-lys-surface-1 p-1 text-[12px] text-lys-primary">
              <option value="">default</option>
              {efforts.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </div>
        </header>

        {error && <div role="alert" className="border-b border-lys-subtle px-4 py-2 text-[13px] text-lys-status-danger">{error}</div>}

        {selected && selected.messages.length === 0 && !busy ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-4 text-center">
            <h2 className="font-display text-[22px] text-lys-primary">What should we plan?</h2>
            <p className="max-w-md text-[13px] text-lys-muted">Ask the orchestrator to draft a brief. It can't start or merge anything.</p>
          </div>
        ) : !selected && !busy ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-4 text-center">
            <h2 className="font-display text-[22px] text-lys-primary">What should we plan?</h2>
            <p className="max-w-md text-[13px] text-lys-muted">Type a message to start a chat. Drafts are saved as Draft, never Ready.</p>
          </div>
        ) : (
          <ChatThread messages={selected?.messages ?? []} busy={busy} />
        )}

        <Composer value={draft} busy={busy} onChange={setDraft} onSend={() => void send()} />
      </section>
    </div>
  );
};

export default CommsRoute;
