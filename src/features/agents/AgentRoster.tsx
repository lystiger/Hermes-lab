import React, { useRef } from 'react';
import { AgentSummary } from '../../api/types';
import { EmptyState, ErrorState, Freshness, LoadingState, StaleNotice, UNKNOWN } from '../../components/DataStates';
import { FilterPills } from '../../components/FilterPills';
import { useArrowNavigation } from '../../components/keyboard';

interface AgentRosterProps {
  agents: AgentSummary[];
  selectedId: string | null;
  filter: string;
  onFilter: (id: string) => void;
  onSelect: (id: string) => void;
  loading: boolean;
  error: unknown;
  updatedAt: number | null;
  onRetry: () => void;
}

/** Statuses as Hermes reports them. The filter shows only statuses that are present, with real counts. */
export function rosterFilterOptions(agents: AgentSummary[]) {
  const counts = new Map<string, number>();
  for (const a of agents) counts.set(a.status, (counts.get(a.status) ?? 0) + 1);
  return [
    { id: 'ALL', label: 'All', count: agents.length },
    ...Array.from(counts.entries()).map(([status, count]) => ({ id: status, label: status.toLowerCase(), count }))
  ];
}

export const AgentRoster: React.FC<AgentRosterProps> = ({
  agents,
  selectedId,
  filter,
  onFilter,
  onSelect,
  loading,
  error,
  updatedAt,
  onRetry
}) => {
  const listRef = useRef<HTMLDivElement>(null);
  useArrowNavigation(listRef);
  const visible = filter === 'ALL' ? agents : agents.filter((a) => a.status === filter);

  return (
    <aside aria-label="Agent roster" className="w-full md:w-72 flex-shrink-0 border-r border-lys-subtle bg-lys-surface-0 flex flex-col">
      <div className="p-3 border-b border-lys-subtle flex flex-col gap-2">
        <div className="flex items-center justify-between font-mono-code text-[11px] tracking-wider text-lys-faint">
          <span>ROSTER · {agents.length}</span>
          <Freshness at={updatedAt} />
        </div>
        <FilterPills label="Filter agents by status" options={rosterFilterOptions(agents)} value={filter} onChange={onFilter} />
      </div>

      {loading && agents.length === 0 && <LoadingState label="Loading roster…" />}
      {Boolean(error) && agents.length === 0 && <ErrorState label="Agent roster" error={error} onRetry={onRetry} />}
      {Boolean(error) && agents.length > 0 && <div className="p-2"><StaleNotice label="Agent roster" error={error} onRetry={onRetry} /></div>}
      {!loading && !error && agents.length === 0 && <EmptyState>Hermes reports no registered agents.</EmptyState>}
      {agents.length > 0 && visible.length === 0 && <EmptyState>No agent has status {filter.toLowerCase()}.</EmptyState>}

      <div ref={listRef} role="listbox" aria-label="Agents" className="flex flex-col p-2 gap-1 overflow-y-auto">
        {visible.map((a, idx) => {
          const selected = a.id === selectedId;
          const running = a.status === 'RUNNING';
          return (
            <button
              key={a.id}
              type="button"
              role="option"
              aria-selected={selected}
              data-nav-item
              onClick={() => onSelect(a.id)}
              style={{ borderLeftColor: a.presentation?.accentColor || 'var(--lys-border-strong)', '--lys-stagger': idx } as React.CSSProperties}
              className={`lys-enter text-left p-2.5 border-l-2 border border-transparent cursor-pointer transition-colors ${
                selected ? 'bg-lys-surface-1 border-lys-subtle' : 'hover:bg-lys-surface-1'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[13px] font-semibold text-lys-primary truncate">{a.displayName}</span>
                <span className={`font-mono-code text-[10px] tracking-wider ${running ? 'text-lys-success' : 'text-lys-muted'}`}>
                  {a.status}
                </span>
              </div>
              <div className="mt-0.5 font-mono-code text-[11px] text-lys-faint truncate">
                {a.role || UNKNOWN} · {a.model || UNKNOWN}
              </div>
              <div className="mt-0.5 text-[11px] text-lys-muted truncate">{a.currentTask || 'no current task reported'}</div>
            </button>
          );
        })}
      </div>
      <p className="mt-auto p-3 font-mono-code text-[10px] text-lys-faint">↑ ↓ move · Enter opens</p>
    </aside>
  );
};
