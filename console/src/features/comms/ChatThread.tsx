import React, { useEffect, useRef } from 'react';
import { Copy } from 'lucide-react';
import { OrchestratorMessage } from '../../api/orchestrator';
import { Markdown } from './Markdown';

const DRAFT_NOTE = 'Saved to LysStack/drafts as Draft. Only you can mark a brief Ready.';

interface ChatThreadProps {
  messages: OrchestratorMessage[];
  busy: boolean;
}

/** The conversation: your messages on the right, replies on the left, each reply can be copied. */
export const ChatThread: React.FC<ChatThreadProps> = ({ messages, busy }) => {
  const end = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'end' });
  }, [messages.length, busy]);

  return (
    <div role="log" aria-live="polite" aria-label="Messages" className="flex-1 min-h-0 overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 py-6 flex flex-col gap-6">
        {messages.map((m, i) => (
          <div key={i} className={`lys-enter flex flex-col gap-2 ${m.role === 'user' ? 'items-end' : 'items-start'}`}>
            {m.role === 'user' ? (
              <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl bg-lys-surface-2 px-4 py-2.5 text-[14px] text-lys-primary">
                {m.content}
              </div>
            ) : (
              <div className="w-full flex flex-col gap-2">
                <div className="text-[14px] text-lys-primary"><Markdown text={m.content} /></div>
                <div className="flex items-center gap-2">
                  <button type="button" aria-label="Copy reply" onClick={() => void navigator.clipboard?.writeText(m.content)}
                    className="p-1 rounded text-lys-faint hover:text-lys-primary hover:bg-lys-surface-2">
                    <Copy size={14} aria-hidden="true" />
                  </button>
                </div>
                {m.drafts && m.drafts.length > 0 && (
                  <div className="rounded border border-lys-subtle px-3 py-2 text-[12px] text-lys-muted">
                    Draft saved: {m.drafts.join(', ')}. {DRAFT_NOTE}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        {busy && (
          <div role="status" className="lys-enter flex items-center gap-2 text-[12px] text-lys-muted">
            <span className="inline-flex gap-1" aria-hidden="true">
              <span className="lys-wave-dot h-1.5 w-1.5 rounded-full bg-lys-muted" style={{ animationDelay: '0ms' }} />
              <span className="lys-wave-dot h-1.5 w-1.5 rounded-full bg-lys-muted" style={{ animationDelay: '150ms' }} />
              <span className="lys-wave-dot h-1.5 w-1.5 rounded-full bg-lys-muted" style={{ animationDelay: '300ms' }} />
            </span>
            Orchestrator is replying…
          </div>
        )}
        <div ref={end} />
      </div>
    </div>
  );
};
