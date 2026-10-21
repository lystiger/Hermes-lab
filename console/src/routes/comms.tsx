import React, { useEffect, useState } from 'react';
import { orchestratorApi, OrchestratorConversation, OrchestratorConversationSummary, OrchestratorOptions } from '../api/orchestrator';
import { Card } from '../components/Card';
import { PageHeader } from '../components/PageHeader';

const DRAFT_NOTE = 'Drafts are saved with status Draft. Only you can mark a brief Ready.';

export const CommsRoute: React.FC = () => {
  const [options, setOptions] = useState<OrchestratorOptions | null>(null);
  const [conversations, setConversations] = useState<OrchestratorConversationSummary[]>([]);
  const [selected, setSelected] = useState<OrchestratorConversation | null>(null);
  const [model, setModel] = useState('claude-sonnet-5-5');
  const [effort, setEffort] = useState('');
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const claude = options?.providers.find((p) => p.id === 'claude');

  const refreshList = () =>
    orchestratorApi.listConversations().then(setConversations).catch((e: Error) => setError(e.message));

  useEffect(() => {
    orchestratorApi.options().then(setOptions).catch((e: Error) => setError(e.message));
    refreshList();
  }, []);

  const open = (id: string) => {
    setError(null);
    orchestratorApi.getConversation(id).then(setSelected).catch((e: Error) => setError(e.message));
  };

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await orchestratorApi.createConversation(model, effort || null);
      setSelected(created);
      await refreshList();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const send = async () => {
    if (!selected || !draft.trim()) return;
    const content = draft.trim();
    setBusy(true);
    setError(null);
    // Show the human's message at once; the server keeps it even if the model call fails.
    setSelected({
      ...selected,
      messages: [...selected.messages, { role: 'user', content, at: new Date().toISOString() }],
    });
    setDraft('');
    try {
      await orchestratorApi.sendMessage(selected.id, content);
      setSelected(await orchestratorApi.getConversation(selected.id));
      await refreshList();
    } catch (e) {
      setError((e as Error).message);
      setSelected(await orchestratorApi.getConversation(selected.id).catch(() => selected));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title="Comms" subtitle="Orchestrator chat · draft only" />
      <div className="grid grid-cols-1 md:grid-cols-[260px_1fr] gap-4 p-6 min-h-0">
        <Card as="section" label="Conversations" bodyClassName="p-3 flex flex-col gap-3">
          <div className="flex flex-col gap-2">
            <label className="text-[11px] uppercase tracking-wider text-lys-faint">Provider</label>
            <div className="text-[13px] text-lys-primary">Claude (chat only, no tools)</div>
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
              onClick={start} disabled={busy}>New chat</button>
          </div>
          <ul className="flex flex-col gap-1">
            {conversations.map((c) => (
              <li key={c.id}>
                <button type="button" onClick={() => open(c.id)}
                  className="w-full text-left text-[13px] text-lys-primary truncate p-1 rounded hover:bg-lys-surface-1">
                  {c.title} <span className="text-lys-faint">· {c.model}{c.effort ? ` · ${c.effort}` : ''}</span>
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <Card as="section" label="Conversation" bodyClassName="p-4 flex flex-col gap-3 min-h-[60vh]">
          {error && <div role="alert" className="text-[13px] text-lys-status-danger">{error}</div>}
          {!selected && <div className="text-[13px] text-lys-muted">Start a new chat or open one from the list.</div>}
          {selected && (
            <>
              <div className="text-[11px] text-lys-faint">Rules snapshot: {selected.system_commit.slice(0, 12)}</div>
              <ol className="flex flex-col gap-3">
                {selected.messages.map((m, i) => (
                  <li key={i} className="flex flex-col gap-1">
                    <span className="text-[11px] uppercase tracking-wider text-lys-faint">{m.role}</span>
                    <div className="whitespace-pre-wrap text-[13px] text-lys-primary">{m.content}</div>
                    {m.drafts && m.drafts.length > 0 && (
                      <div className="text-[12px] text-lys-muted">
                        Saved to LysStack/drafts: {m.drafts.join(', ')}. {DRAFT_NOTE}
                      </div>
                    )}
                  </li>
                ))}
              </ol>
              <form className="mt-auto flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); send(); }}>
                <label htmlFor="comms-input" className="sr-only">Message</label>
                <textarea id="comms-input" rows={4} value={draft} onChange={(e) => setDraft(e.target.value)}
                  className="bg-lys-surface-1 text-lys-primary text-[13px] p-2 rounded" />
                <button type="submit" disabled={busy || !draft.trim()}
                  className="self-end text-[13px] p-1 px-3 rounded border border-lys-subtle">
                  {busy ? 'Waiting for the model…' : 'Send'}
                </button>
              </form>
            </>
          )}
        </Card>
      </div>
    </>
  );
};

export default CommsRoute;
