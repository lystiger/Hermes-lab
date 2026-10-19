import { describe, it, expect, beforeEach } from 'vitest';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { EventsRoute } from '../routes/events';
import { OverviewRoute } from '../routes/index';
import { useConsoleStore, sortNewestFirst } from '../stores/useConsoleStore';
import { traceSourceName } from '../api/actors';
import { TraceEvent } from '../api/types';

const ev = (id: string, rawTs: number, source = { id: 'claude', kind: 'agent', displayName: 'Claude' }): TraceEvent => ({
  id,
  ts: '10:00:00.000',
  rawTs,
  source,
  kind: 'agent.started',
  detail: `detail ${id}`,
  dur: '—'
});

beforeEach(() => {
  useConsoleStore.setState({ allEvents: [], eFilter: 'All' });
});

describe('event order: newest first everywhere', () => {
  it('history that arrives oldest first is stored newest first', () => {
    useConsoleStore.getState().setInitialEvents([ev('a', 1), ev('b', 2), ev('c', 3)]);
    expect(useConsoleStore.getState().allEvents.map((e) => e.id)).toEqual(['c', 'b', 'a']);
  });

  it('a late, older event is placed by its time, not at the top', () => {
    useConsoleStore.setState({ allEvents: sortNewestFirst([ev('a', 1), ev('c', 3)]) });
    useConsoleStore.getState().addTraceEvent(ev('late', 2));
    expect(useConsoleStore.getState().allEvents.map((e) => e.id)).toEqual(['c', 'late', 'a']);
  });

  it('the Events log lists rows newest first, and the overview trace does too', () => {
    useConsoleStore.getState().setInitialEvents([ev('old', 1), ev('mid', 2), ev('new', 3)]);
    const { unmount } = render(
      <MemoryRouter>
        <EventsRoute />
      </MemoryRouter>
    );
    const rows = within(screen.getByRole('log', { name: 'Events' })).getAllByRole('button');
    expect(rows[0]).toHaveTextContent('detail new');
    expect(rows[2]).toHaveTextContent('detail old');
    unmount();

    const overview = render(
      <MemoryRouter>
        <OverviewRoute />
      </MemoryRouter>
    );
    expect(overview.container.textContent!.indexOf('detail new')).toBeLessThan(overview.container.textContent!.indexOf('detail old'));
    overview.unmount();
  });

  it('the new-events pill still counts arrivals while the list is frozen in the new order', () => {
    useConsoleStore.getState().setInitialEvents([ev('old', 1), ev('new', 2)]);
    const page = document.createElement('div');
    page.className = 'lys-scroll';
    let top = 0;
    Object.defineProperty(page, 'scrollTop', { configurable: true, get: () => top, set: (v: number) => (top = v) });
    document.body.appendChild(page);
    const { unmount } = render(
      <MemoryRouter>
        <EventsRoute />
      </MemoryRouter>,
      { container: page.appendChild(document.createElement('div')) }
    );
    act(() => {
      top = 300;
      page.dispatchEvent(new Event('scroll'));
    });
    act(() => {
      useConsoleStore.getState().addTraceEvent(ev('arrival', 3));
    });
    const log = screen.getByRole('log', { name: 'Events' });
    expect(within(log).getAllByRole('button')).toHaveLength(2);
    expect(screen.getByRole('button', { name: /1 new event/ })).toBeInTheDocument();
    unmount();
    page.remove();
  });
});

describe('source names: registered actor names, not raw ids', () => {
  it('shows the registered name for known actors and the event name otherwise', () => {
    expect(traceSourceName({ id: 'openrig', displayName: 'Openrig' })).toBe('OpenRig');
    expect(traceSourceName({ id: 'hermes_runner', displayName: 'Hermes_runner' })).toBe('Hermes Runner');
    expect(traceSourceName({ id: 'hermes_message_router', displayName: 'Hermes Message Router' })).toBe('Hermes Message Router');
  });

  it('rows and the source filter use the registered name', () => {
    useConsoleStore.getState().setInitialEvents([ev('o1', 1, { id: 'openrig', kind: 'runtime', displayName: 'Openrig' })]);
    render(
      <MemoryRouter>
        <EventsRoute />
      </MemoryRouter>
    );
    expect(within(screen.getByRole('log', { name: 'Events' })).getByText('OpenRig')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^OpenRig\s*1/ })).toBeInTheDocument();
    expect(screen.queryByText('Openrig')).not.toBeInTheDocument();
  });
});
