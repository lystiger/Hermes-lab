import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { DesignRoute } from '../routes/design';

const manifest = {
  project: 'unigreen', generated: '2026-10-21', sheet: 'sheet.png', contrast: 'contrast.json',
  directions: [
    { id: 'a-family-fresh', label: 'A · Family fresh', detail: 'detail-a-family-fresh.png' },
    { id: 'b-clean-eco', label: 'B · Clean eco', detail: 'detail-b-clean-eco.png' },
  ],
  decision: null, decision_note: 'Nothing is chosen until then.',
};

function mockFetch({ decision = null as Record<string, string> | null, post = { ok: true, status: 201, json: async () => ({}) } } = {}) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/manifest.json')) return { ok: true, status: 200, json: async () => manifest };
    if (init?.method === 'POST') return post;
    return { ok: true, status: 200, json: async () => ({ decision, directions: [] }) };
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('choosing a design direction', () => {
  it('records a choice with its reason, and shows it as chosen', async () => {
    const fetchMock = mockFetch();
    render(<MemoryRouter><DesignRoute /></MemoryRouter>);
    fireEvent.click((await screen.findAllByRole('button', { name: 'Choose this direction' }))[1]);

    fireEvent.change(screen.getByRole('textbox', { name: 'Reason' }), { target: { value: 'Clear for buyers and calm.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm choice' }));

    await waitFor(() => expect(screen.getByText(/Chosen: B · Clean eco/)).toBeInTheDocument());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(JSON.parse(String(post![1]!.body))).toEqual({ direction: 'b-clean-eco', reason: 'Clear for buyers and calm.' });
  });

  it('locks the other directions once one is chosen, until the choice is changed', async () => {
    mockFetch({ decision: { direction: 'a-family-fresh', label: 'A · Family fresh', reason: 'Already decided here.', date: '2026-10-21' } });
    render(<MemoryRouter><DesignRoute /></MemoryRouter>);
    const buttons = await screen.findAllByRole('button', { name: 'Choose this direction' });

    expect(buttons.every((b) => b.hasAttribute('disabled'))).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: 'Change decision' }));

    expect(screen.getAllByRole('button', { name: 'Choose this direction' })[1]).toBeEnabled();
  });

  it('keeps Confirm off until the reason is long enough', async () => {
    mockFetch();
    render(<MemoryRouter><DesignRoute /></MemoryRouter>);
    fireEvent.click((await screen.findAllByRole('button', { name: 'Choose this direction' }))[0]);

    fireEvent.change(screen.getByRole('textbox', { name: 'Reason' }), { target: { value: 'short' } });

    expect(screen.getByRole('button', { name: 'Confirm choice' })).toBeDisabled();
  });

  it('shows the server refusal instead of pretending it worked', async () => {
    mockFetch({ post: { ok: false, status: 400, json: async () => ({ detail: 'already the chosen direction' }) } });
    render(<MemoryRouter><DesignRoute /></MemoryRouter>);
    fireEvent.click((await screen.findAllByRole('button', { name: 'Choose this direction' }))[0]);
    fireEvent.change(screen.getByRole('textbox', { name: 'Reason' }), { target: { value: 'A long enough reason.' } });

    fireEvent.click(screen.getByRole('button', { name: 'Confirm choice' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('already the chosen direction');
  });

  it('disables choosing when the API is down, and says why', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.endsWith('/manifest.json')) return { ok: true, status: 200, json: async () => manifest };
      throw new Error('network down');
    }));
    render(<MemoryRouter><DesignRoute /></MemoryRouter>);

    expect(await screen.findByText(/Hermes API is not reachable/)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Choose this direction' })[0]).toBeDisabled();
  });
});
