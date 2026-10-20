import React, { useRef } from 'react';
import { AgentSummary } from '../../api/types';
import { EmptyState, ErrorState, Freshness, LoadingState, StaleNotice } from '../../components/DataStates';
import { FilterPills } from '../../components/FilterPills';
import { useArrowNavigation } from '../../components/keyboard';
import { AgentPresence } from './AgentPresence';

interface AgentRosterProps {
  agents: AgentSummary[];
  selectedId: string | null;
  filter: string;
  onFilter: (id: string) => void;
  onSelect: (id: string) => void;
  loading: boolean;
  error: unknown;
  stale?: boolean;
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

/** Roster (research §1.1): a vertical list of agent presence cards with accent edges and portraits. */
export const AgentRoster: React.FC<AgentRosterProps> = ({ agents, selectedId, filter, onFilter, onSelect, loading, error, stale = false, updatedAt, onRetry }) => {
  const listRef = useRef<HTMLDivElement>(null);
  useArrowNavigation(listRef);
  const visible = filter === 'ALL' ? agents : agents.filter((a) => a.status === filter);

  return (
    <aside aria-label="Agent roster" className="w-full lg:w-80 shrink-0 border-r border-lys-subtle bg-lys-surface-0 flex flex-col">
      <div className="p-4 border-b border-lys-subtle flex flex-col gap-3">
        <div className="flex items-center justify-between text-[11px] tracking-wider uppercase text-lys-faint">
          <span>Roster · {agents.length}</span>
          <Freshness at={updatedAt} />
        </div>
        <FilterPills label="Filter agents by status" options={rosterFilterOptions(agents)} value={filter} onChange={onFilter} />
      </div>

      {loading && agents.length === 0 && <LoadingState label="Loading roster…" />}
      {Boolean(error) && agents.length === 0 && <ErrorState label="Agent roster" error={error} onRetry={onRetry} />}
      {Boolean(stale) && <div className="p-2"><StaleNotice label="Agent roster" error={error} onRetry={onRetry} /></div>}
      {!loading && !error && agents.length === 0 && <EmptyState>No agents</EmptyState>}
      {agents.length > 0 && visible.length === 0 && <EmptyState>No {filter.toLowerCase()} agents</EmptyState>}

      <div ref={listRef} role="listbox" aria-label="Agents" className="flex flex-col p-3 gap-2 overflow-y-auto">
        {visible.map((a, idx) => (
          <AgentPresence key={a.id} agent={a} selected={a.id === selectedId} index={idx} onClick={() => onSelect(a.id)} />
        ))}
      </div>
    </aside>
  );
};
