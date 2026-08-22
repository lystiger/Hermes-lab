import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function getFilesRecursively(dir: string): string[] {
  let results: string[] = [];
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat && stat.isDirectory()) {
      if (file !== 'node_modules' && file !== '.git' && file !== 'dist') {
        results = results.concat(getFilesRecursively(filePath));
      }
    } else if (file.endsWith('.ts') || file.endsWith('.tsx')) {
      results.push(filePath);
    }
  }
  return results;
}

describe('Architectural Boundary Enforcement', () => {
  it('strictly prohibits direct imports from api/mock in UI, routes, stores, components, and hooks', () => {
    const srcDir = path.resolve(__dirname, '..');
    const allFiles = getFilesRecursively(srcDir);

    const violations: { file: string; line: string }[] = [];

    const allowedPaths = [
      path.normalize('src/api/adapters/mockAdapter.ts'),
      path.normalize('src/api/mock/'),
      path.normalize('src/__tests__/')
    ];

    for (const file of allFiles) {
      const isAllowed = allowedPaths.some((p) => file.includes(p));
      if (isAllowed) continue;

      const content = fs.readFileSync(file, 'utf8');
      const lines = content.split('\n');

      lines.forEach((line: string, idx: number) => {
        if (
          (line.includes("from './mock/") ||
           line.includes('from "../mock/') ||
           line.includes("from '../../mock/") ||
           line.includes('from "../api/mock/') ||
           line.includes("from '../../api/mock/")) &&
          !line.trim().startsWith('//')
        ) {
          violations.push({
            file: path.relative(srcDir, file),
            line: `L${idx + 1}: ${line.trim()}`
          });
        }
      });
    }

    expect(
      violations,
      `Detected unauthorized direct mock layer imports:\n${JSON.stringify(violations, null, 2)}`
    ).toEqual([]);
  });
});
