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

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderRoute() {
  return render(<MemoryRouter><DesignRoute /></MemoryRouter>);
}

describe('Design route', () => {
  it('shows the decision state, the directions, and the first direction detail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => manifest }));

    renderRoute();

    expect(await screen.findByText('No direction chosen yet')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'A · Family fresh' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('img', { name: /A · Family fresh/ })).toHaveAttribute('src', '/design/unigreen/detail-a-family-fresh.png');
  });

  it('switches to another direction when its tab is chosen', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => manifest }));
    renderRoute();
    await screen.findByRole('tab', { name: 'B · Clean eco' });

    fireEvent.click(screen.getByRole('tab', { name: 'B · Clean eco' }));

    await waitFor(() => expect(screen.getByRole('img', { name: /B · Clean eco/ })).toHaveAttribute('src', '/design/unigreen/detail-b-clean-eco.png'));
  });

  it('says the boards are missing when the manifest cannot be read', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));

    renderRoute();

    expect(await screen.findByRole('alert')).toHaveTextContent('manifest not found (404)');
  });
});
