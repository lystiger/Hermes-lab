import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { Header } from '../components/Header';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="*" element={<Header />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('Header placement', () => {
  it('takes no space on pages without a back link', () => {
    const { container } = renderAt('/comms');

    expect(container.querySelector('header')).toBeNull();
  });

  it('keeps the back link on an agent page, and no connection status in the bar', () => {
    renderAt('/agents/claude');

    expect(screen.getByRole('button', { name: /Agents/ })).toBeInTheDocument();
    expect(screen.queryByText(/reachable|unreachable|connecting|degraded/i)).toBeNull();
  });
});
