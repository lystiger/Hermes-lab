import React, { useState } from 'react';
import { Check, Pencil, Plus, Trash2, X } from 'lucide-react';
import { OrchestratorConversationSummary } from '../../api/orchestrator';

interface ChatSidebarProps {
  conversations: OrchestratorConversationSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onRename: (id: string, title: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}

const ICON_BUTTON = 'p-1 rounded text-lys-muted hover:text-lys-primary hover:bg-lys-surface-2';

/** The chat list: new chat, select, rename in place, and delete after a second click. */
export const ChatSidebar: React.FC<ChatSidebarProps> = ({ conversations, selectedId, onSelect, onNew, onRename, onDelete }) => {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [confirmingId, setConfirmingId] = useState<string | null>(null);

  const saveRename = async (id: string) => {
    const title = editTitle.trim();
    setEditingId(null);
    if (title) await onRename(id, title);
  };

  return (
    <nav aria-label="Chats" className="flex flex-col gap-2 h-full min-h-0">
      <button type="button" onClick={onNew}
        className="flex items-center gap-2 px-2 py-2 rounded text-[13px] text-lys-primary hover:bg-lys-surface-2">
        <Plus size={16} aria-hidden="true" /> New chat
      </button>

      <ul className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-0.5">
        {conversations.map((c) => {
          const active = c.id === selectedId;
          if (editingId === c.id) {
            return (
              <li key={c.id} className="flex items-center gap-1 px-1">
                <input aria-label="Chat title" autoFocus value={editTitle} maxLength={120}
                  onChange={(e) => setEditTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void saveRename(c.id);
                    if (e.key === 'Escape') setEditingId(null);
                  }}
                  className="flex-1 min-w-0 bg-lys-surface-0 border border-lys-default rounded px-2 py-1 text-[13px] text-lys-primary" />
                <button type="button" aria-label="Save title" onClick={() => void saveRename(c.id)} className={ICON_BUTTON}><Check size={14} /></button>
                <button type="button" aria-label="Cancel rename" onClick={() => setEditingId(null)} className={ICON_BUTTON}><X size={14} /></button>
              </li>
            );
          }
          if (confirmingId === c.id) {
            return (
              <li key={c.id} className="flex items-center justify-between gap-2 px-2 py-1.5 text-[12px] text-lys-status-danger">
                <span>Delete this chat?</span>
                <span className="flex gap-1">
                  <button type="button" onClick={() => { setConfirmingId(null); void onDelete(c.id); }}
                    className="px-2 py-0.5 rounded border border-lys-default text-lys-status-danger">Delete</button>
                  <button type="button" onClick={() => setConfirmingId(null)}
                    className="px-2 py-0.5 rounded border border-lys-subtle text-lys-muted">Cancel</button>
                </span>
              </li>
            );
          }
          return (
            <li key={c.id} className={`group flex items-center gap-1 rounded px-1 ${active ? 'bg-lys-surface-2' : 'hover:bg-lys-surface-1'}`}>
              <button type="button" onClick={() => onSelect(c.id)} aria-current={active ? 'true' : undefined}
                className="flex-1 min-w-0 text-left py-1.5 px-1 text-[13px] text-lys-primary truncate">
                {c.title}
              </button>
              <span className="flex opacity-0 group-hover:opacity-100 focus-within:opacity-100">
                <button type="button" aria-label={`Rename ${c.title}`} className={ICON_BUTTON}
                  onClick={() => { setEditingId(c.id); setEditTitle(c.title); }}><Pencil size={13} /></button>
                <button type="button" aria-label={`Delete ${c.title}`} className={ICON_BUTTON}
                  onClick={() => setConfirmingId(c.id)}><Trash2 size={13} /></button>
              </span>
            </li>
          );
        })}
      </ul>
    </nav>
  );
};
