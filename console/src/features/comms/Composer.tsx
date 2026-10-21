import React from 'react';
import { ArrowUp } from 'lucide-react';

interface ComposerProps {
  value: string;
  busy: boolean;
  onChange: (value: string) => void;
  onSend: () => void;
}

/** The message box at the bottom: Enter sends, Shift+Enter starts a new line. */
export const Composer: React.FC<ComposerProps> = ({ value, busy, onChange, onSend }) => {
  const canSend = !busy && value.trim().length > 0;
  return (
    <form className="mx-auto w-full max-w-3xl px-4 pb-4"
      onSubmit={(e) => { e.preventDefault(); if (canSend) onSend(); }}>
      <div className="flex items-end gap-2 rounded-2xl border border-lys-default bg-lys-surface-1 px-3 py-2 focus-within:border-lys-strong">
        <label htmlFor="comms-input" className="sr-only">Message</label>
        <textarea id="comms-input" rows={1} value={value} disabled={busy}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              if (canSend) onSend();
            }
          }}
          placeholder="Message the orchestrator"
          className="max-h-48 flex-1 resize-none bg-transparent py-1.5 text-[14px] text-lys-primary outline-none placeholder:text-lys-faint" />
        <button type="submit" disabled={!canSend} aria-label="Send message"
          className="grid h-8 w-8 place-items-center rounded-full bg-lys-primary text-lys-surface-0 disabled:opacity-30">
          <ArrowUp size={16} aria-hidden="true" />
        </button>
      </div>
      <p className="mt-2 text-center text-[11px] text-lys-faint">The orchestrator drafts briefs only. It cannot start, cancel or merge runs.</p>
    </form>
  );
};
