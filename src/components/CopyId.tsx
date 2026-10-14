import React, { useEffect, useState } from 'react';

/** An identifier with a copy button. Copy failures (no clipboard permission) are shown, not swallowed. */
export const CopyId: React.FC<{ value: string; className?: string }> = ({ value, className = '' }) => {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle');

  useEffect(() => {
    if (state === 'idle') return;
    const id = setTimeout(() => setState('idle'), 1500);
    return () => clearTimeout(id);
  }, [state]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setState('copied');
    } catch {
      setState('failed');
    }
  };

  return (
    <span className={`inline-flex items-center gap-1.5 min-w-0 ${className}`}>
      <span className="font-mono-code break-all">{value}</span>
      <button
        type="button"
        onClick={copy}
        aria-label={`Copy ${value}`}
        className="font-sans text-[10px] text-lys-faint hover:text-lys-primary border border-lys-subtle hover:border-lys-strong px-1 cursor-pointer shrink-0"
      >
        {state === 'copied' ? 'copied' : state === 'failed' ? 'no clipboard' : 'copy'}
      </button>
    </span>
  );
};
