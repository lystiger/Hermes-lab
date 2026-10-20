import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Sidebar } from '../components/Sidebar';
import { EventsRoute } from '../routes/events';
import { Icon } from '../components/Icon';
import { useConsoleStore } from '../stores/useConsoleStore';
import { SIDEBAR_STORAGE_KEY } from '../components/sidebarState';
import { installLiveHermes } from './support/liveHermes';
import { TraceEvent } from '../api/types';
import { Activity } from 'lucide-react';

/** In-memory localStorage: the test environment does not provide one on window. */
function installStorage(impl: Partial<Storage> | null) {
  const data = new Map<string, string>();
  const store = impl ?? {
    getItem: (k: string) => (data.has(k) ? data.get(k)! : null),
    setItem: (k: string, v: string) => void data.set(k, String(v)),
    removeItem: (k: string) => void data.delete(k),
    clear: () => data.clear(),
    key: () => null,
    get length() {
      return data.size;
    }
  };
  Object.defineProperty(window, 'localStorage', { configurable: true, value: store });
}

/** Makes matchMedia answer for the sidebar's narrow-window query. */
function setNarrow(narrow: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query.includes('max-width: 1099px') ? narrow : false,
    media: query,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    onchange: null,
    dispatchEvent: () => false
  }));
}

function renderSidebar() {
  return render(
    <MemoryRouter>
      <Sidebar />
    </MemoryRouter>
  );
}

beforeEach(() => {
  installStorage(null);
  window.localStorage.clear();
  setNarrow(false);
  installLiveHermes();
  useConsoleStore.setState({ allEvents: [] });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('M7 sidebar: collapse, memory, keyboard, narrow windows', () => {
  it('starts expanded, collapses with the button, and remembers the choice', () => {
    const { unmount } = renderSidebar();
    const aside = document.getElementById('app-sidebar')!;
    expect(aside).toHaveAttribute('data-collapsed', 'false');

    fireEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }));
    expect(aside).toHaveAttribute('data-collapsed', 'true');
    expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe('1');
    unmount();

    renderSidebar();
    expect(document.getElementById('app-sidebar')).toHaveAttribute('data-collapsed', 'true');
  });

  it('the "[" key toggles the sidebar, but not while typing in a field', () => {
    renderSidebar();
    const aside = document.getElementById('app-sidebar')!;
    fireEvent.keyDown(document, { key: '[' });
    expect(aside).toHaveAttribute('data-collapsed', 'true');
    fireEvent.keyDown(document, { key: '[' });
    expect(aside).toHaveAttribute('data-collapsed', 'false');

    const field = document.createElement('input');
    document.body.appendChild(field);
    field.focus();
    fireEvent.keyDown(field, { key: '[' });
    expect(aside).toHaveAttribute('data-collapsed', 'false');
    field.remove();
  });

  it('auto-collapses below 1100px, and the user can open it for the view', () => {
    setNarrow(true);
    renderSidebar();
    const aside = document.getElementById('app-sidebar')!;
    expect(aside).toHaveAttribute('data-collapsed', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Expand sidebar' }));
    expect(aside).toHaveAttribute('data-collapsed', 'false');
  });

  it('keeps working when localStorage is blocked', () => {
    const blocked = () => {
      throw new Error('blocked');
    };
    installStorage({ getItem: blocked, setItem: blocked } as any);
    renderSidebar();
    fireEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }));
    expect(document.getElementById('app-sidebar')).toHaveAttribute('data-collapsed', 'true');
  });
});

describe('M7 icons: every icon-only control is labelled', () => {
  it('a labelled icon is an image with an accessible name; a decorative one is hidden', () => {
    const { container, rerender } = render(<Icon icon={Activity} label="Hermes Reachable" />);
    expect(screen.getByRole('img', { name: 'Hermes Reachable' })).toBeInTheDocument();
    rerender(<Icon icon={Activity} />);
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });

  it('collapsed navigation keeps an accessible name and tooltip for every page', () => {
    setNarrow(false);
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, '1');
    renderSidebar();
    for (const label of ['Overview', 'Queue', 'Agents', 'Usage', 'Events', 'Execution', 'Settings']) {
      const link = screen.getByRole('link', { name: label });
      expect(link).toHaveAttribute('title', label);
    }
    expect(screen.getByRole('button', { name: 'Expand sidebar' })).toHaveAttribute('title', expect.stringContaining('Expand sidebar'));
  });
});

describe('M7 events: new events pill instead of moving what the user reads', () => {
  const ev = (id: string, rawTs: number): TraceEvent => ({
    id,
    ts: '10:00:00.000',
    rawTs,
    source: { id: 'claude', kind: 'agent', displayName: 'Claude' },
    kind: 'agent.started',
    detail: `detail ${id}`,
    dur: '—'
  });

  function scrollingPage() {
    const page = document.createElement('div');
    page.className = 'lys-scroll';
    let top = 0;
    Object.defineProperty(page, 'scrollTop', { configurable: true, get: () => top, set: (v: number) => (top = v) });
    page.scrollTo = ((opts: ScrollToOptions) => {
      top = opts.top ?? 0;
      page.dispatchEvent(new Event('scroll'));
    }) as typeof page.scrollTo;
    document.body.appendChild(page);
    return page;
  }

  it('freezes the list while scrolled down, counts arrivals, and releases on "back to newest"', () => {
    useConsoleStore.setState({ allEvents: [ev('e3', 3), ev('e2', 2), ev('e1', 1)] });
    const page = scrollingPage();
    const { unmount } = render(
      <MemoryRouter>
        <EventsRoute />
      </MemoryRouter>,
      { container: page.appendChild(document.createElement('div')) }
    );
    const log = screen.getByRole('log', { name: 'Events' });
    expect(within(log).getAllByRole('button')).toHaveLength(3);

    // The operator scrolls down to read.
    act(() => {
      (page as any).scrollTop = 400;
      page.dispatchEvent(new Event('scroll'));
    });

    // A new event arrives while they read.
    act(() => {
      useConsoleStore.getState().addTraceEvent(ev('e4', 4));
    });
    expect(within(log).getAllByRole('button')).toHaveLength(3);
    expect(screen.getByRole('button', { name: /1 new event · back to newest/ })).toBeInTheDocument();

    // Back to the newest: the pill goes and the new event is shown.
    fireEvent.click(screen.getByRole('button', { name: /1 new event · back to newest/ }));
    act(() => page.dispatchEvent(new Event('scroll')));
    expect(screen.queryByRole('button', { name: /new event/ })).not.toBeInTheDocument();
    expect(within(log).getAllByRole('button')).toHaveLength(4);
    unmount();
    page.remove();
  });

  it('shows new events at once while the user is at the top', () => {
    useConsoleStore.setState({ allEvents: [ev('e1', 1)] });
    const page = scrollingPage();
    const { unmount } = render(
      <MemoryRouter>
        <EventsRoute />
      </MemoryRouter>,
      { container: page.appendChild(document.createElement('div')) }
    );
    act(() => {
      useConsoleStore.getState().addTraceEvent(ev('e2', 2));
    });
    expect(within(screen.getByRole('log', { name: 'Events' })).getAllByRole('button')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: /new event/ })).not.toBeInTheDocument();
    unmount();
    page.remove();
  });
});

describe('M7 sync: a busy stream cannot starve the screen', () => {
  it('applies the newest response that finishes, even when refreshes keep superseding each other', async () => {
    const { act: a } = await import('@testing-library/react');
    const { hermesApi } = await import('../api/client');
    const { useJobs } = await import('../api/hooks');
    const { renderHook } = await import('@testing-library/react');
    const pending: Array<{ resolve: (v: any) => void }> = [];
    vi.spyOn(hermesApi, 'getJobs').mockImplementation(
      () => new Promise((resolve) => pending.push({ resolve }))
    );
    const { result } = renderHook(() => useJobs());
    // Three refreshes start before any finishes, as they do when events arrive quickly.
    for (let i = 0; i < 2; i++) {
      a(() => useConsoleStore.setState({ jobRuntimeVersion: useConsoleStore.getState().jobRuntimeVersion + 1 }));
    }
    expect(pending).toHaveLength(3);
    // The middle one finishes first and is shown, rather than waiting for the last.
    await a(async () => pending[1].resolve([{ id: 'middle', title: 'm', repository: 'r', status: 'RUNNING', assignedAgentIds: [] }]));
    expect(result.current.jobs.map((j) => j.id)).toEqual(['middle']);
    // The first to start finishes last: it is older than what is shown, so it is ignored.
    await a(async () => pending[0].resolve([{ id: 'oldest', title: 'o', repository: 'r', status: 'QUEUED', assignedAgentIds: [] }]));
    expect(result.current.jobs.map((j) => j.id)).toEqual(['middle']);
  });
});
