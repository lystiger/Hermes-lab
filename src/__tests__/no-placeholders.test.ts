import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..');

const FORBIDDEN = [
  '#142',
  'VehicleStateStore',
  'moveinmate',
  '$4.12',
  '58%',
  'SIMULATED',
  '~37 min',
  'v0.1.0',
  'raise cap',
  'alert(',
  'Phase 4',
  'Not reported by Hermes'
];

function getFilesRecursively(target: string): string[] {
  const stat = fs.statSync(target);
  if (!stat.isDirectory()) {
    return [target];
  }
  const results: string[] = [];
  const entries = fs.readdirSync(target);
  for (const entry of entries) {
    const full = path.join(target, entry);
    const s = fs.statSync(full);
    if (s.isDirectory()) {
      results.push(...getFilesRecursively(full));
    } else if (/\.(tsx?|jsx?|css)$/.test(entry)) {
      results.push(full);
    }
  }
  return results;
}

describe('No Placeholders Guard', () => {
  it('scanned files contain no forbidden demo strings or placeholders', () => {
    const scanTargets = [
      path.join(ROOT, 'components'),
      path.join(ROOT, 'routes'),
      path.join(ROOT, 'features'),
      path.join(ROOT, 'stores'),
      path.join(ROOT, 'api/adapters/httpAdapter.ts')
    ];

    const allFiles: string[] = [];
    for (const t of scanTargets) {
      if (fs.existsSync(t)) {
        allFiles.push(...getFilesRecursively(t));
      }
    }

    const violations: { file: string; line: number; forbidden: string; text: string }[] = [];

    for (const file of allFiles) {
      const content = fs.readFileSync(file, 'utf8');
      const lines = content.split('\n');
      lines.forEach((line, index) => {
        for (const token of FORBIDDEN) {
          if (line.includes(token)) {
            violations.push({
              file: path.relative(ROOT, file),
              line: index + 1,
              forbidden: token,
              text: line.trim()
            });
          }
        }
      });
    }

    expect(
      violations,
      `Found forbidden placeholder strings:\n${JSON.stringify(violations, null, 2)}`
    ).toEqual([]);
  });
});
