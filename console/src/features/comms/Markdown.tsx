import React from 'react';

/**
 * A small Markdown subset for chat replies: paragraphs, bullet and numbered lists, pipe tables,
 * **bold** and `code`. It builds React elements, never HTML, so reply text cannot inject markup.
 */

type Block =
  | { kind: 'paragraph'; lines: string[] }
  | { kind: 'list'; ordered: boolean; items: string[] }
  | { kind: 'table'; header: string[]; rows: string[][] };

const TABLE_SEPARATOR = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;
const BULLET = /^\s*[-*]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;

function cells(line: string): string[] {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
}

export function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === '') {
      i += 1;
      continue;
    }
    if (line.includes('|') && i + 1 < lines.length && TABLE_SEPARATOR.test(lines[i + 1]) && lines[i + 1].includes('-')) {
      const header = cells(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].includes('|') && lines[i].trim() !== '') {
        rows.push(cells(lines[i]));
        i += 1;
      }
      blocks.push({ kind: 'table', header, rows });
      continue;
    }
    const bullet = BULLET.exec(line);
    const numbered = NUMBERED.exec(line);
    if (bullet || numbered) {
      const ordered = !bullet;
      const pattern = ordered ? NUMBERED : BULLET;
      const items: string[] = [];
      while (i < lines.length) {
        const match = pattern.exec(lines[i]);
        if (!match) break;
        items.push(match[1]);
        i += 1;
      }
      blocks.push({ kind: 'list', ordered, items });
      continue;
    }
    const paragraph: string[] = [];
    while (i < lines.length && lines[i].trim() !== '' && !BULLET.test(lines[i]) && !NUMBERED.test(lines[i])
      && !(lines[i].includes('|') && i + 1 < lines.length && TABLE_SEPARATOR.test(lines[i + 1]))) {
      paragraph.push(lines[i]);
      i += 1;
    }
    blocks.push({ kind: 'paragraph', lines: paragraph });
  }
  return blocks;
}

/** **bold** and `code` inside a line. Everything else is plain text. */
export function inline(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter((p) => p !== '');
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return <code key={i} className="rounded bg-lys-surface-2 px-1 font-mono-code text-[12px]">{part.slice(1, -1)}</code>;
    }
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
}

export const Markdown: React.FC<{ text: string }> = ({ text }) => {
  const blocks = parseBlocks(text);
  return (
    <div className="flex flex-col gap-3">
      {blocks.map((block, i) => {
        if (block.kind === 'table') {
          return (
            <div key={i} className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-[13px]">
                <thead>
                  <tr>
                    {block.header.map((h, j) => (
                      <th key={j} scope="col" className="border-b border-lys-default px-3 py-1.5 font-semibold text-lys-primary">{inline(h)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {block.rows.map((row, r) => (
                    <tr key={r} className="border-b border-lys-subtle">
                      {row.map((cell, c) => (
                        <td key={c} className="px-3 py-1.5 align-top text-lys-primary">{inline(cell)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        if (block.kind === 'list') {
          const ListTag = block.ordered ? 'ol' : 'ul';
          return (
            <ListTag key={i} className={`flex flex-col gap-1 pl-5 ${block.ordered ? 'list-decimal' : 'list-disc'}`}>
              {block.items.map((item, j) => <li key={j}>{inline(item)}</li>)}
            </ListTag>
          );
        }
        return <p key={i} className="leading-relaxed">{inline(block.lines.join(' '))}</p>;
      })}
    </div>
  );
};
