import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { Markdown, parseBlocks } from '../features/comms/Markdown';

describe('chat reply formatting', () => {
  it('draws a pipe table with headers and rows', () => {
    const text = 'Agents:\n\n| Agent | Model | Left |\n|---|---|---|\n| Claude | sonnet | 92% |\n| Codex | gpt | 4% |';

    render(<Markdown text={text} />);

    const table = screen.getByRole('table');
    expect(within(table).getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['Agent', 'Model', 'Left']);
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[1]).getByText('4%')).toBeInTheDocument();
  });

  it('keeps bullets, numbered items, bold and code', () => {
    render(<Markdown text={'- **Avoid** `agy`\n- check quota\n\n1. first\n2. second'} />);

    expect(screen.getByText('Avoid').tagName).toBe('STRONG');
    expect(screen.getByText('agy').tagName).toBe('CODE');
    expect(screen.getAllByRole('list')).toHaveLength(2);
    expect(screen.getByText('second')).toBeInTheDocument();
  });

  it('shows angle brackets as text, never as markup', () => {
    render(<Markdown text={'<script>alert(1)</script> and **ok**'} />);

    expect(screen.getByText(/<script>alert\(1\)<\/script>/)).toBeInTheDocument();
    expect(document.querySelector('script')).toBeNull();
  });

  it('splits blocks in order', () => {
    const blocks = parseBlocks('intro line\n| a | b |\n|---|---|\n| 1 | 2 |\n- item');

    expect(blocks.map((b) => b.kind)).toEqual(['paragraph', 'table', 'list']);
  });
});
