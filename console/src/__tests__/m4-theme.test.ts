import { describe, it, expect, vi, afterEach } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

vi.hoisted(() => {
  delete process.env.VITE_LYSCONTROL_MOCK;
});

import { AGENT_ACCENT_VARS, actorAccent, agentAccent } from '../theme/agents';
import { resolveActorPresentation } from '../api/actors';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const read = (rel: string) => fs.readFileSync(path.join(ROOT, rel), 'utf8');
const css = read('src/styles/globals.css');

/** Token values as declared in :root. Each one must exist exactly once. */
function declared(name: string): string {
  const m = css.match(new RegExp(`${name}:\\s*([^;]+);`));
  if (!m) throw new Error(`token ${name} is not declared in globals.css`);
  return m[1].trim();
}

const EXPECTED: Record<string, string> = {
  '--lys-bg-base': '#08090B',
  '--lys-surface-0': '#0C0E12',
  '--lys-surface-1': '#12151B',
  '--lys-surface-2': '#181D25',
  '--lys-surface-interactive': '#202632',
  '--lys-border-subtle': '#1C222C',
  '--lys-border-default': '#28303E',
  '--lys-border-strong': '#3D485C',
  '--lys-text-primary': '#E6E9ED',
  '--lys-text-secondary': '#B7BEC7',
  '--lys-text-muted': '#8C949F',
  '--lys-text-faint': '#868F9B',
  '--lys-status-success': '#3FB950',
  '--lys-status-warning': '#E3A008',
  '--lys-status-danger': '#F5626A',
  '--lys-status-info': '#58A6FF',
  '--lys-accent-gold': '#CBA35C',
  '--lys-accent-gold-hover': '#E8CE9B',
  '--lys-accent-sky': '#7FB3D5',
  '--lys-accent-violet': '#A78BFA',
  '--lys-agent-claude': '#CCA27D',
  '--lys-agent-codex': '#7A8ECE',
  '--lys-agent-gemini': '#9686E1',
  '--lys-agent-hermes': '#CBA35C',
  '--lys-ink': '#000000'
};

describe('M4 tokens: one source of truth in globals.css', () => {
  it('declares every colour token with its agreed value', () => {
    for (const [name, value] of Object.entries(EXPECTED)) {
      expect(declared(name).toUpperCase(), name).toBe(value);
    }
  });

  it('exposes every colour token as a Tailwind theme colour', () => {
    for (const name of Object.keys(EXPECTED)) {
      // --lys-bg-base -> --color-lys-base, --lys-text-muted -> --color-lys-muted, --lys-agent-claude -> --color-lys-agent-claude
      const short = name.replace(/^--lys-(bg|text|status|accent|border)-/, '').replace(/^--lys-/, '');
      const utility = `--color-lys-${short}`;
      expect(css, utility).toContain(`${utility}: var(${name});`);
    }
  });

  it('declares typography, motion and geometry tokens', () => {
    for (const name of [
      '--lys-font-display',
      '--lys-font-body',
      '--lys-font-mono',
      '--lys-duration-instant',
      '--lys-duration-fast',
      '--lys-duration-normal',
      '--lys-duration-deliberate',
      '--lys-ease-hsr',
      '--lys-ease-zzz',
      '--lys-ease-standard',
      '--lys-radius-md',
      '--lys-clip-chamfer'
    ]) {
      expect(declared(name), name).toBeTruthy();
    }
  });
});

describe('M4 token usage: components reference tokens, not literal colours', () => {
  const SKIP = [/__tests__/, /api\/mock\//, /api\/adapters\/mockAdapter\.ts$/, /theme\//];
  function files(dir: string, out: string[] = []): string[] {
    for (const f of fs.readdirSync(dir)) {
      const p = path.join(dir, f);
      if (fs.statSync(p).isDirectory()) files(p, out);
      else if (/\.(tsx|ts)$/.test(f) && !SKIP.some((re) => re.test(p))) out.push(p);
    }
    return out;
  }

  it('contains no hard-coded hex or rgba colour in UI code', () => {
    const offenders: string[] = [];
    for (const file of files(path.join(ROOT, 'src'))) {
      const lines = fs.readFileSync(file, 'utf8').split('\n');
      lines.forEach((line, i) => {
        if (/#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{8}\b|rgba?\(/.test(line)) {
          offenders.push(`${path.relative(ROOT, file)}:${i + 1}: ${line.trim().slice(0, 120)}`);
        }
      });
    }
    expect(offenders, offenders.join('\n')).toEqual([]);
  });

  it('gives every agent a single accent variable, resolved in one module', () => {
    expect(AGENT_ACCENT_VARS).toEqual({
      claude: 'var(--lys-agent-claude)',
      codex: 'var(--lys-agent-codex)',
      gemini: 'var(--lys-agent-gemini)',
      agy: 'var(--lys-agent-gemini)',
      hermes: 'var(--lys-agent-hermes)'
    });
    for (const v of Object.values(AGENT_ACCENT_VARS)) {
      expect(declared(v.replace(/^var\(|\)$/g, ''))).toBeTruthy();
    }
    expect(agentAccent('Claude')).toBe('var(--lys-agent-claude)');
  });

  it('applies the agent variable even when the backend sends its own colour', () => {
    expect(actorAccent('gemini', '#5B8CFF')).toBe('var(--lys-agent-gemini)');
    expect(actorAccent('unknown-x', '#123456')).toBe('#123456');
    const resolved = resolveActorPresentation('codex');
    expect(resolved.accentColor).toBe('var(--lys-agent-codex)');
  });
});

describe('M4 fonts: OFL families bundled, not fetched', () => {
  it('bundles Outfit, Plus Jakarta Sans and JetBrains Mono through @fontsource', () => {
    const pkg = JSON.parse(read('package.json'));
    for (const dep of ['@fontsource/outfit', '@fontsource/plus-jakarta-sans', '@fontsource/jetbrains-mono']) {
      expect(pkg.dependencies?.[dep] ?? pkg.devDependencies?.[dep], dep).toBeTruthy();
    }
    const main = read('src/main.tsx');
    expect(main).toContain("import '@fontsource/outfit/400.css';");
    expect(main).toContain("import '@fontsource/plus-jakarta-sans/400.css';");
    expect(main).toContain("import '@fontsource/jetbrains-mono/400.css';");
  });

  it('no longer loads fonts from Google', () => {
    expect(read('index.html')).not.toContain('fonts.googleapis.com');
  });

  it('uses the families for display, body and mono, with tabular figures on metrics', () => {
    expect(css).toMatch(/h1,\s*h2,\s*h3\s*\{\s*font-family:\s*var\(--lys-font-display\)/);
    expect(css).toMatch(/--font-mono:\s*var\(--lys-font-mono\)/);
    expect(css).toMatch(/\.font-mono-code,\s*\.lys-metric\s*\{\s*font-variant-numeric:\s*tabular-nums/);
  });
});

describe('M4 motion: tokens on transitions and entry only, nothing perpetual at rest', () => {
  it('drives hover and state transitions from the motion tokens', () => {
    expect(css).toMatch(/\.transition-colors[\s\S]*?transition-duration:\s*var\(--lys-duration-fast\)/);
    expect(css).toMatch(/\.transition-colors[\s\S]*?transition-timing-function:\s*var\(--lys-ease-standard\)/);
  });

  it('fades every page in on navigation and each new chat message on entry', () => {
    const layout = fs.readFileSync(path.join(ROOT, 'src/components/Layout.tsx'), 'utf8');
    expect(layout).toContain('key={location.pathname} className="lys-enter');
    const thread = fs.readFileSync(path.join(ROOT, 'src/features/comms/ChatThread.tsx'), 'utf8');
    expect(thread).toContain('lys-enter flex flex-col gap-2');
  });

  it('caps list stagger at 180ms total (20ms steps, 9 steps)', () => {
    expect(css).toContain('animation-delay: calc(min(var(--lys-stagger, 0), 9) * 20ms);');
  });

  it('uses no infinite animation in components except the cube while hovered', () => {
    const SKIP = [/__tests__/, /api\/mock\//];
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const f of fs.readdirSync(dir)) {
        const p = path.join(dir, f);
        if (fs.statSync(p).isDirectory()) walk(p);
        else if (/\.(tsx|ts)$/.test(f) && !SKIP.some((re) => re.test(p))) {
          fs.readFileSync(p, 'utf8').split('\n').forEach((line, i) => {
            if (line.includes('infinite') && !line.includes('group-hover:animate-')) {
              offenders.push(`${path.relative(ROOT, p)}:${i + 1}`);
            }
          });
          if (fs.readFileSync(p, 'utf8').includes('animate-pulse')) offenders.push(`${path.relative(ROOT, p)}: animate-pulse`);
        }
      }
    };
    walk(path.join(ROOT, 'src'));
    expect(offenders).toEqual([]);
  });

  it('collapses animation and transition for prefers-reduced-motion', () => {
    const block = css.match(/@media \(prefers-reduced-motion: reduce\) \{([\s\S]*?)\n\}/);
    expect(block).not.toBeNull();
    expect(block![1]).toContain('animation-duration: 0.01ms !important');
    expect(block![1]).toContain('animation-iteration-count: 1 !important');
    expect(block![1]).toContain('transition-duration: 0.01ms !important');
  });

  it('starts live motion off when the system asks for reduced motion', async () => {
    vi.resetModules();
    vi.stubGlobal('matchMedia', (q: string) => ({ matches: q.includes('reduce'), media: q, addEventListener() {}, removeEventListener() {} }));
    const { useConsoleStore } = await import('../stores/useConsoleStore');
    expect(useConsoleStore.getState().liveMotion).toBe(false);
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });
});

describe('M4 contrast: WCAG 2.1 AA for every text token on every surface', () => {
  const DOC = read('docs/design/m4-decisions.md');
  const luminance = (hex: string) => {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const ratio = (a: string, b: string) => {
    const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
    return (x + 0.05) / (y + 0.05);
  };

  const rows = DOC.split('\n').filter((l) => /^\|\s*--lys-[\w-]+\s*\|\s*#[0-9A-Fa-f]{6}\s*\|/.test(l));

  it('has the contrast table in the decisions document', () => {
    expect(rows.length).toBeGreaterThanOrEqual(16 * 5);
  });

  it('covers every text token on every surface, and every row passes AA (4.5:1)', () => {
    const fgTokens = [
      '--lys-text-primary', '--lys-text-secondary', '--lys-text-muted', '--lys-text-faint',
      '--lys-status-success', '--lys-status-warning', '--lys-status-danger', '--lys-status-info',
      '--lys-accent-gold', '--lys-accent-gold-hover', '--lys-accent-sky', '--lys-accent-violet',
      '--lys-agent-claude', '--lys-agent-codex', '--lys-agent-gemini', '--lys-agent-hermes'
    ];
    const bgTokens = ['--lys-bg-base', '--lys-surface-0', '--lys-surface-1', '--lys-surface-2', '--lys-surface-interactive'];
    const seen = new Set<string>();
    for (const row of rows) {
      const cells = row.split('|').map((c) => c.trim());
      const [, fgName, fgHex, bgName, bgHex, recorded, result] = cells;
      expect(declared(fgName).toUpperCase(), fgName).toBe(fgHex);
      expect(declared(bgName).toUpperCase(), bgName).toBe(bgHex);
      const actual = ratio(fgHex, bgHex);
      expect(Math.abs(actual - Number(recorded)), `${fgName} on ${bgName}`).toBeLessThan(0.01);
      expect(actual, `${fgName} on ${bgName}`).toBeGreaterThanOrEqual(4.5);
      expect(result).toBe('AA pass');
      seen.add(`${fgName}|${bgName}`);
    }
    for (const fg of fgTokens) for (const bg of bgTokens) expect(seen.has(`${fg}|${bg}`), `${fg} on ${bg}`).toBe(true);
  });
});
