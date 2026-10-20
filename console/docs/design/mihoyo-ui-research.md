# HoYoverse (miHoYo) UI/UX Design System Research & Operator Console Adaptation

> **Document Classification**: Design Architecture & Ergonomics Research  
> **Target Application**: [LysControl](file:///home/lystiger/Projects/LysControl) (React 19, Tailwind CSS 4, Vite 8, Zustand)  
> **Backend Ecosystem**: Hermes Runtime API (AI Coding Agents: Claude, Codex, AGY on OpenRig Seats)  
> **Target File Location**: `~/Projects/LysControl/docs/design/mihoyo-ui-research.md`  

---

## Executive Summary

This research investigates the user interface (UI), interaction ergonomics (UX), and motion design languages across HoYoverse's flagship titles—**Genshin Impact**, **Honkai: Star Rail (HSR)**, **Zenless Zone Zero (ZZZ)**, and **Honkai Impact 3rd (HI3)**. 

While these games are commercial entertainment products, their underlying interface engineering represents an industry benchmark in **dense data presentation, multi-layered progressive disclosure, tactile spatial hierarchy, and fatigue-resistant animation**. LysControl is an operator console for the Hermes runtime, managing autonomous engineering agents executing complex code modification jobs across backend execution seats. By translating HoYoverse's visual and spatial mastery into a high-utility developer console—while deliberately stripping out gacha mechanics, artificial friction, and theatrical particle bloat—we can create an interface that feels extraordinarily responsive, tactile, and clear under heavy cognitive loads.

---

## 1. Information Hierarchy & Navigation: Managing Dense Systems

Modern HoYoverse games manage staggering volumes of tabular attributes, hierarchical equipment, contextual skill trees, multi-stage quest logs, and live combat state. Despite running on devices ranging from 6-inch mobile screens to 65-inch 4K displays, their interfaces rarely feel incomprehensible.

```text
┌────────────────────────────────────────────────────────────────────────┐
│                       HOYOVERSE NAVIGATION PARADIGM                    │
│                                                                        │
│   PRIMARY ANCHOR              INSPECTOR / MATRIX      ACTION FOOTER    │
│  ┌───────────────┐           ┌──────────────────┐    ┌───────────────┐ │
│  │ 3D Entity /   │           │ Tabbed Modular   │    │ Tactile CTA / │ │
│  │ Hero Card /   │ ────────> │ Attribute Blocks │ ──>│ Contextual    │ │
│  │ Spatial Stage │           │ & Interactive    │    │ Keybind Strip │ │
│  │               │           │ Nodes            │    │               │ │
│  └───────────────┘           └──────────────────┘    └───────────────┘ │
│         ▲                             │                       │        │
│         └────────────── PERSISTENT SPATIAL CONTEXT ───────────┘        │
└────────────────────────────────────────────────────────────────────────┘
```

### 1.1 Structural Navigation Paradigms

1. **The Roster Split-Pane Anchor (Genshin, HSR, ZZZ)**:
   - *Architecture*: The screen divides into an invariant 40–45% visual focal pane (showing the character model, live idle animation, or card illustration) and a 55–60% modular data pane.
   - *Cognitive Anchor*: Even as the user drills three levels deep into sub-menus (Attributes → Relic Detail → Enhancement Tier), the entity being modified remains visible on the left. The operator never suffers spatial disorientation.
   - *Navigation Rail*: HSR employs a vertical rail of circular avatar thumbnails or cards with instant keyboard/gamepad paging (`Q`/`E` or `1-4`). Swapping entities retains the current sub-tab on the inspector pane (e.g., flipping between characters stays on their "Traces/Skills" tab).

2. **Multi-Level Progressive Disclosure**:
   - Rather than dumping all properties into a monolithic scrollable document, HoYoverse segments data into strict ontological layers:
     - **Level 1 (Glanceable Summary)**: Core HP, Attack, Defense, Active Element/Role, Current Equipment.
     - **Level 2 (Deep Inspector)**: Tabbed sub-panels (Attributes, Equipment, Skill Tree, Constellations/Eidolons, Biography/Logs).
     - **Level 3 (Modal Drawer/Flyout)**: Clicking any individual stat or skill opens a focused side-sheet revealing exact formulas, coefficient percentages, and source attribution.

3. **Missions, Assignments, and Commissions**:
   - *HSR Assignments Board & Genshin Adventurer Handbook*: Categorizes tasks by geographic scope, difficulty tier, and duration.
   - *Two-State Layout*: A master list of missions on the left (with urgent/tracked indicators) dynamically drives an objective-and-rewards briefing pane on the right.
   - *ZZZ Inter-Knot Commission Board*: Formats missions as an urban web forum / BBS thread list. Each entry displays author avatar, urgency tag, reward bounty chips, and thread status. Clicking expands a tactile "Cassette Tape" or "Contract Dossier".

4. **Event Pages and Codex Archives**:
   - HoYoverse interfaces manage chronological archives through **Timeline Steppers** and **Filterable Codices**.
   - Filters are never buried inside dropdown menus; they exist as persistent horizontal pill strips with live counter badges (e.g., `All (48)`, `Main Story (4)`, `Exploration (12)`, `Urgent (2)`).

---

## 2. Visual Systems Across Games

| Dimension | Genshin Impact | Honkai: Star Rail (HSR) | Zenless Zone Zero (ZZZ) | Honkai Impact 3rd (HI3) |
| :--- | :--- | :--- | :--- | :--- |
| **Aesthetic Core** | Ethereal High-Fantasy & Celestial Astronomy | Neo-Cosmic Sci-Fi & Astral Elegance | Analog Street-Punk & Lo-Fi Cybernetic CRT | Tactical Military HUD & Cyber-Valkyrie Command |
| **Base Palette** | Warm dark stone (`#141824`), obsidian, gold filigree | Deep cosmic navy (`#0B0E14`), starry black, platinum | Matte industrial black (`#101012`), concrete grey, stark chalk | Deep navy-slate (`#0C1322`), gunmetal, glowing wireframe blue |
| **Accent System** | 7 Elemental hues (Teal, Amber, Violet, Jade, Azure, Red, Frost) | Path & Combat Type colors (Quantum Indigo, Imaginary Gold, Fire Orange) | High-voltage neon (Acid Yellow `#E5FF00`, Hazard Orange `#FF5500`, Cyan `#00F0FF`) | Neon cyan (`#00E5FF`), alert orange (`#FF6D00`), emergency red |
| **Typography** | Classical serifed display headings + ultra-clean humanist body | Sharp, geometric sans-serif + high-precision tabular numerals | Heavy ultra-bold industrial sans, angled italics, stencil accents | Monospace tactical labels, clean technical DIN-style sans |
| **Surfaces & Borders** | Translucent smoky glass with delicate 1px engraved gold filigree borders | Frosted obsidian acrylic, chamfered corner notches, hairline borders | Physical raised cards, diagonal hazard stripes, halftone screen dots | Hexagonal clips (`clip-path: polygon`), holographic HUD frames |
| **Iconography** | Stylized celestial constellations and organic elemental emblems | Sleek minimalist vector glyphs, path sigils inside circular badges | Heavy-line graffiti icons, VHS tracking symbols, cassette icons | Tactical crosshairs, radar reticles, military badge emblems |

```text
┌────────────────────────────────────────────────────────────────────────┐
│                      VISUAL SURFACE COMPARISON                         │
│                                                                        │
│   GENSHIN IMPACT              HONKAI: STAR RAIL         ZENLESS ZONE 0 │
│  ┌──────────────────┐        ┌──────────────────┐    ┌───────────────┐ │
│  │ ╭──────────────╮ │        │ ╱‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾╲│    │ █▀▀▀▀▀▀▀▀▀▀▀█ │ │
│  │ │ Gold Filigree│ │        ││ Frosted Acrylic ││    │ █ ACID PUNK █ │ │
│  │ │ Smoky Glass  │ │        ││ Hairline Border ││    │ █ Chamfered █ │ │
│  │ ╰──────────────╯ │        │ ╲_______________╱│    │ █ 0 4px 0 Shd █ │ │
│  └──────────────────┘        └──────────────────┘    └───────────────┘ │
│     Warm Fantasy               Cosmic Tech              Analog Street  │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Color Coding & Semantic Hierarchy
- **Functional Semantics vs Cosmetic Flavour**: HoYoverse enforces strict chromatic grammar. Backgrounds are deliberately kept ultra-dark and desaturated (`#0A0B0E` to `#161922`) to allow accent colors to function as optical beacons.
- **Rarity / Priority Tiering**:
  - *Tier 1 (Base / Standard)*: Neutral grey/blue (`#8C949F` / `#4A5568`).
  - *Tier 2 (Advanced / Specialized)*: Electric Purple / Amethyst (`#A855F7` / `#9333EA`).
  - *Tier 3 (Master / Apex / P0)*: Sovereign Star-Gold / Amber (`#F59E0B` / `#CBA35C`).
  - *Alert / Failure*: High-luminance Crimson (`#F2555A` / `#EF4444`).

### 2.2 Typography & Number Styling
- **Tabular Lining Numerals (`font-variant-numeric: tabular-nums`)**: Critical stats, damage values, resource counters, and timers never jitter horizontally during updates. Every glyph occupies an identical optical width.
- **Unit Separation**: Values and their units are treated as separate optical hierarchies. In `142.8 ms` or `42.5k tok`, the number is styled at `text-base font-bold text-white`, while the unit is styled at `text-xs font-normal text-muted-400 ml-1`.
- **Exaggerated Numerical Counters**: Key totals (credits, stamina, level caps) use oversized weights (600–800) with generous character tracking (`tracking-wide` or `tracking-tight` depending on geometric vs industrial styling).

### 2.3 Depth, Glassmorphism, and Surface Borders
- **Backdrop Blurs**: HoYoverse relies on high-quality multi-pass gaussian blurs (`backdrop-filter: blur(12px) saturate(140%)`) tinted with deep neutral black (`rgba(12, 14, 18, 0.75)`). This prevents background world noise from reducing foreground contrast.
- **Chamfered Geometry**: Instead of generic round borders (`rounded-lg`), HSR and ZZZ use geometric chamfers (diagonal 45° cut corners) created via CSS `clip-path: polygon(...)` or SVG border masks.
- **Tactile Physical Elevation (ZZZ)**: Rather than relying solely on blurred box shadows, ZZZ uses hard physical drops (`box-shadow: 0 4px 0 #18191C`), mimicking physical rubber or acrylic keys on an industrial control deck.

---

## 3. Motion Language: Tactility, Easing & Fatigue Prevention

Motion in HoYoverse interfaces is never merely decorative; it provides **proprioceptive feedback** to confirm state mutations and guide visual attention.

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        MOTION DURATION SPECTRUM                        │
│                                                                        │
│   0ms      100ms         180ms           260ms               380ms     │
│   ├──────────┼─────────────┼───────────────┼───────────────────┤       │
│   Instant    Micro-Snap    Standard UI     Panel Slide /       Modal   │
│   Input      Hover / Tab   Dropdown / Card Drawer Transition   Entry   │
│              Selection     Expansion                           Overlay │
│                                                                        │
│   EASING:    ZZZ Kinetic   Standard Tech   HSR Smooth-Glide    Decel   │
│              Elastic       cubic(0.4,0,0.2) cubic(0.16,1,0.3,1) Exit    │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Easing Curves & Timing Breakdown
1. **The HSR "Smooth-Glide" (`cubic-bezier(0.16, 1, 0.3, 1)`)**:
   - Used for main screen switches, drawer expansions, and large panel transitions.
   - High initial velocity with an extraordinarily graceful deceleration tail. It feels sophisticated, weightless, and precise.
2. **The ZZZ "Kinetic Snap" (`cubic-bezier(0.34, 1.25, 0.64, 1)`)**:
   - Used for active buttons, tab indicator switches, and badge pops.
   - Features a controlled 5–10% micro-overshoot that settles immediately. It imparts a tactile, mechanical click feeling.
3. **The Micro-Feedback Duration (120ms–180ms)**:
   - Hover state changes and border-glow illuminations never exceed 150ms. Anything slower feels sluggish; anything faster feels glitchy.

### 3.2 Choreography & Staggering
- When a dense data grid opens, elements do not appear simultaneously. They enter using a **staggered cascade**:
  - Main background container opens at `0ms`.
  - Header & primary navigation land at `40ms`.
  - Content cards/rows stagger in at `20ms` intervals (clapped at a maximum total sequence duration of `180ms` to prevent waiting).
  - Data within the cards (numbers, meters) counts up or expands smoothly over `250ms`.

### 3.3 Motion Fatigue Prevention Principles
Enterprise and daily operator tools must avoid the "flashy game demo" trap. HoYoverse mitigates visual fatigue through four key rules:
1. **Spatial Anchoring**: Critical navigation anchors (top header, primary tab bar, status bar) *never move*. Motion is strictly confined to content viewports within static bounding boxes.
2. **Asymmetric Durations**: Entrances are expressive (`220ms`), but dismissals and back actions are lightning-fast (`120ms` linear or ease-in) to prioritize task momentum.
3. **Strict Amplitude Boundaries**: Positional translations during reveals never exceed `8px` to `16px`. Excessive screen-wide sliding causes nausea during repetitive usage.
4. **Settle States**: Once an animation finishes, all motion ceases completely. There are no perpetual breathing glows or distracting pulsing borders in active work areas.

---

## 4. Boundary Analysis: What Does NOT Transfer to Productivity Tools

To build an extraordinary operator console, we must identify which gacha game patterns are toxic to engineering productivity.

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        TRANSFERABILITY AUDIT                           │
│                                                                        │
│   ❌ DO NOT TRANSFER (ANTI-PATTERNS)     ✅ TRANSFER WITH PRIDE        │
│   ──────────────────────────────────     ───────────────────────       │
│   • Multi-second unskippable gacha pulls • Glancable status hierarchies│
│   • Loot box mystery & hidden states    • Multi-tiered stat inspection │
│   • Artificial waiting ceremonies       • Tabular lining numerals      │
│   • Continuous GPU-draining particles   • 40/60 roster/detail split    │
│   • Low-contrast fantasy text           • Snappy mechanical feedback   │
│   • Obscuring errors with confetti      • Circular/segmented stamina   │
└────────────────────────────────────────────────────────────────────────┘
```

1. **Unskippable Reveal Ceremonies**:
   - *Game Pattern*: A 5-star character pull triggers a 6-second theatrical cinematic with spinning constellations and orchestral fanfare.
   - *Why It Fails in LysControl*: An operator launching an autonomous agent job wants to verify execution start instantly. Any delay between clicking "Dispatch" and seeing the live process PID is catastrophic friction.
   - *Productivity Translation*: Replace the ceremony with a crisp, 140ms micro-pop badge and immediate telemetry stream engagement.

2. **Dopamine Traps & Ambiguous Probabilities**:
   - *Game Pattern*: Obscuring drop rates, currency conversion layers, and progress percentages behind celebratory loot chests.
   - *Why It Fails in LysControl*: Operators require deterministic, mathematically transparent telemetry. Resource limits, quota reset times, and token burn rates must be shown as absolute numbers with exact decimal precision.

3. **Continuous Particle Systems & Canvas Loops**:
   - *Game Pattern*: Ambient stardust particles, floating embers, and 60fps WebGL background meshes.
   - *Why It Fails in LysControl*: An operator console often runs continuously in background browser tabs or on secondary laptop screens. Perpetual WebGL rendering drains battery life, spikes CPU temperatures, and competes with Hermes runtime build processes.
   - *Productivity Translation*: Pure CSS hardware-accelerated transitions (`transform`, `opacity`) with zero continuous loop animations when idle.

4. **Theatrical Error Obfuscation**:
   - *Game Pattern*: Smoothing over failures with playful character chibis or generic "network error" popups.
   - *Why It Fails in LysControl*: In an engineering console, errors are first-class citizens. Stack traces, seat disconnect reasons, tool timeouts, and HTTP status codes must be prominently surfaced with copyable identifiers and direct links to the event stream.

---

## 5. Mapping to the LysControl Operator Console

Here we map HoYoverse UI paradigms directly to the five primary functional domains of LysControl.

```text
┌────────────────────────────────────────────────────────────────────────┐
│                     LYSCONTROL MAPPING BLUEPRINT                       │
│                                                                        │
│   HOYOVERSE PARADIGM                   LYSCONTROL DOMAIN               │
│   ──────────────────                   ─────────────────               │
│   Character Roster & Dossier    ───>   Agents Page (/agents)           │
│   Missions & Commission Board   ───>   Jobs & Queue (/queue)           │
│   Party Deployment & Combat Deck───>   Execution & Seats (/execution)  │
│   Codex Archive & Travel Log    ───>   Events & Audit Log (/events)    │
│   Stamina & Resource Fuel       ───>   Provider Telemetry (/usage)     │
└────────────────────────────────────────────────────────────────────────┘
```

---

### 5.1 Agents Page (`/agents` and `/agents/$agentId`): The Operator Roster & Character Dossier

The current LysControl agent routes feature agent portraits, lane cards, and context meters. We can elevate this into a high-precision **HSR Roster + ZZZ Agent Dossier**.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ AGENTS ROSTER · HERMES OPERATOR REGISTRY                                          [+ NEW AGENT]   │
├──────────────────────────┬───────────────────────────────────────────────────────────────────────┤
│ ROSTER FILTER: [ALL] [BUSY]│ CLAUDE-3-7-SONNET · ANTHROPIC                   [DISPATCH TASK] [...]│
│ ┌──────────────────────┐ │ ┌──────────────────┬────────────────────────────────────────────────┐ │
│ │ ● CLAUDE-3-7-SONNET  │ │ │ [CHARACTER CARD] │ CORE SPECS & ATTRIBUTES                        │ │
│ │   Coding Specialist  │ │ │                  │ • Model: claude-3-7-sonnet-20250219            │ │
│ │   Tokens: 412k (82%) │ │ │   Tactile Avatar │ • Backend: OpenRig Seat #01                    │ │
│ ├──────────────────────┤ │ │   Status: IDLE   │ • Active Job: #job-8924 (Fix Hydration Bug)    │ │
│ │ ● CODEX-5-PRO        │ │ │   Phase: AWAIT   │ • Temperature: 0.20  • Max Tokens: 8,192        │ │
│ │   Architecture Lead  │ │ └──────────────────┴────────────────────────────────────────────────┘ │
│ │   Tokens: 120k (24%) │ │ ┌───────────────────────────────────────────────────────────────────┐ │
│ ├──────────────────────┤ │ │ CONTEXT WINDOW QUOTA (HSR STAMINA BAR STYLE)                      │ │
│ │ ● AGY-GEMINI-FLASH   │ │ │ [██████████████████████████████░░░░░░░░░░] 164,280 / 200,000 tok  │ │
│ │   Speed / Exploration│ │ └───────────────────────────────────────────────────────────────────┘ │
│ │   Tokens: 18k (9%)   │ │ ┌──────────────────┬────────────────────────────────────────────────┐ │
│ └──────────────────────┘ │ │ CAPABILITY RADAR │ TOOL MATRIX & PERMISSIONS                      │ │
│ [1-3] Quick Switch Key   │ │ │ (Visual Hex    │ [✓] filesystem.read   [✓] git.commit           │ │
│                          │ │ │  Attribute Grid│ [✓] terminal.exec     [✗] production.deploy    │ │
│                          │ │ └──────────────────┴────────────────────────────────────────────────┘ │
└──────────────────────────┴───────────────────────────────────────────────────────────────────────┘
```

#### Layout & Structural Recommendations
- **Persistent Roster Column (Left 25%)**: Vertical list of agent lane cards. Each card displays:
  - Agent avatar with live ambient status pip (Green pulse = Running, Amber = Awaiting tool response, Grey = Idle).
  - Agent Name & provider badge.
  - Micro-segmented context window capacity bar.
  - Keyboard accelerator badge (`[1]`, `[2]`, `[3]`).
- **Hero Dossier Inspector (Right 75%)**:
  - *Top Header*: Bold, oversized typographic title with agent accent color stripe, model identifier, and quick-action buttons ("Dispatch Task", "Emergency Intervene", "Evacuate Context").
  - *Entity Anchor (Left)*: The existing 3D Agent Portrait / WebP character card rendered with a subtle chamfered armor border (`clip-armor`).
  - *Attribute Matrix (Right)*: Clean two-column grid showing current execution seat, runtime process ID, active task ID, and temperature settings.
  - *Context Window Gauge*: Styled as an HSR Ultimate/Energy meter—segmented blocks that change color as tokens cross 50% (amber) and 80% (danger red).
  - *Tool & Permission Matrix*: Inspired by HSR's "Traces" tree—a structured interactive node grid displaying enabled tools with execution count metrics.

#### Interaction Design
- **Keyboard Instant-Paging**: Hitting `1`, `2`, or `3` instantly transitions the inspector without full page reload.
- **Micro-Interaction**: Clicking an individual tool node opens a quick slide-over drawer showing recent execution logs for that specific tool.

---

### 5.2 Jobs & Queue Page (`/queue`): The Mission Commission Board

Transform the pipeline view into a tactile **Commission Dispatch Board** inspired by Genshin's Adventurer Handbook and ZZZ's Inter-Knot Commission BBS.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ JOB PIPELINE & QUEUE · 4 RUNNING · 2 BLOCKED · 8 PENDING                          [+ CREATE JOB] │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ CONCURRENCY LANES: [REPO: LysOmarchy (2/2)]  [REPO: LysControl (1/2)]  [REPO: Hermes-lab (1/1)]   │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ QUEUE MATRIX: [ALL (14)]  [RUNNING (4)]  [BLOCKED (2)]  [QUEUED (8)]       SORT: [PRIORITY ▼]    │
│                                                                                                  │
│ ┌─ P0 CRITICAL ────────────────────────────────────────────────────────────────────────────────┐ │
│ │ #JOB-9012  Fix authentication token desync in Hermes SSE adapter                             │ │
│ │ Target: lystiger/LysControl • Branch: fix/sse-auth • Assigned: CLAUDE-3-7-SONNET             │ │
│ │ Status: [████████████████░░░░░░░░░░░░░░░░] Phase 3/5: Running Vitest Suite (82s)            │ │
│ │ [INSPECT LIVE LOGS]  [FORCE RETRY]  [REASSIGN SEAT]                                          │ │
│ └──────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                  │
│ ┌─ P1 URGENT ──────────────────────────────────────────────────────────────────────────────────┐ │
│ │ #JOB-9015  Implement Chamfered Border Tokens in Tailwind CSS 4                               │ │
│ │ Target: lystiger/LysControl • Branch: feat/tokens • Assigned: CODEX-5-PRO                    │ │
│ │ Status: [WAITING ON SEAT AVAILABILITY] • Queue Position: #1 (Est. 45s)                       │ │
│ └──────────────────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

#### Layout & Structural Recommendations
- **Top Concurrency Lane Strip**: Horizontal cards showing per-repository execution capacity (e.g., `LysControl: 2/2 Active Seats`). Inspired by HSR's Expedition dispatch tracker.
- **Commission Cards**:
  - *Priority Header Strip*: Chamfered color banner on the left edge (P0 Red, P1 Amber, P2 Slate).
  - *Mission Metadata*: Job ID, human-readable objective description, repository target, and assigned agent chip.
  - *Progress Meter*: Segmented visual progress bar reflecting pipeline phases (`Plan → Code → Test → Review`).
  - *Direct Action Toolbar*: Inline buttons to open the modal terminal, reassign backend seats, or cancel.

#### Interaction Design
- **Priority Drag-and-Drop or Rapid Keybinds**: Move jobs up or down the dispatch order with immediate visual spring feedback.
- **Failed State Reveal**: If a job fails, the card does not vanish or silently highlight red. It displays an amber "Mission Interrupted" warning ribbon with a single-click "Analyze Failure with Agent" CTA.

---

### 5.3 Execution Page (`/execution`): Deployed Party & Active Seat Cockpit

The `/execution` route tracks OpenRig backend seats, daemon states, and execution resources. This maps seamlessly to the **HoYoverse Deployed Party & Combat Seat Matrix**.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ EXECUTION COCKPIT · HERMES RUNTIME BACKENDS                          HEARTBEAT: 24ms [CONNECTED]│
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ BACKEND STRIP: [HERMES: ONLINE (v0.8.2)]  [HERDR: 4 SANDBOXES]  [OPENRIG: 4/4 SEATS PROVISIONED]│
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ACTIVE DEPLOYED PARTY (4 OPERATIONAL SEATS)                                                      │
│                                                                                                  │
│ ┌─ SEAT 01: OPENRIG ────────┐ ┌─ SEAT 02: OPENRIG ────────┐ ┌─ SEAT 03: HERDR ──────────┐ ...    │
│ │ OPERATOR: CLAUDE-3-7      │ │ OPERATOR: CODEX-5         │ │ OPERATOR: AGY-GEMINI       │       │
│ │ Task: Run Test Suite      │ │ Task: Refactor Hooks      │ │ Task: Scan AST Imports     │       │
│ │ Memory: 1.2 GB / 4.0 GB   │ │ Memory: 820 MB / 4.0 GB   │ │ Memory: 410 MB / 2.0 GB    │       │
│ │ [███████████████░░░░░░░░] │ │ [██████████░░░░░░░░░░░░░] │ │ [█████░░░░░░░░░░░░░░░░░░] │       │
│ │ Pooled TTL: 04:22 remaining│ │ Pooled TTL: 12:10 remaining│ │ Mode: Disposable Sandbox  │       │
│ │ [STDOUT] [RECYCLE] [KILL] │ │ [STDOUT] [RECYCLE] [KILL] │ │ [ATTACH TERMINAL]          │       │
│ └───────────────────────────┘ └───────────────────────────┘ └────────────────────────────┘       │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ LIVE EXECUTION TIMELINE · REAL-TIME DISPATCH TRACE                                               │
│ 14:32:01.104 [SEAT-01] [TOOL.EXEC] bash -c "npm run test" -> exit 0 (14 passed)                 │
│ 14:32:04.882 [SEAT-02] [FILE.WRITE] src/routes/execution.tsx (+42 lines)                         │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

#### Layout & Structural Recommendations
- **Party Deck Grid (Top 55%)**: Exactly 4 large, structured cards representing active runtime seats (mirroring a 4-character battle party in HSR or Genshin).
  - Each seat card acts as an active physical module with glowing status borders:
    - *Slot Number & Backend Type* (e.g., `SEAT 01 · OPENRIG POOLED`).
    - *Occupant Agent Avatar & Name*.
    - *Current Task Summary & Live Runtime Counter*.
    - *Memory & Compute Gauges*: Real-time circular or progress meters.
    - *Pooled Seat Countdown*: Styled like an ability cooldown timer, ticking down until the idle seat is recycled.
- **Execution Telemetry Feed (Bottom 45%)**: A dense monospace stream displaying real-time `execution.*` events with color-coded origin tags.

#### Interaction Design
- **Seat Inspection Drawer**: Clicking any seat card expands a side-drawer showing the live stdout/stderr stream from that specific OpenRig seat without leaving the overview.
- **Seat Recycling**: Hovering over the "Recycle" button turns the border amber with an instant hover-scale micro-animation.

---

### 5.4 Events Page (`/events`): The Expedition Log & Codex Archive

The `/events` page handles high-frequency SSE event streams. It should be structured as an **Archive Codex & Expedition Travel Log**.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ RUNTIME CODEX & AUDIT LOG                                           STREAM: [● LIVE SSE 120 evt/m]│
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ FILTER TABS: [ALL (1,248)] [HERMES (42)] [CLAUDE (612)] [CODEX (480)] [ERRORS (4)] [TOOLS (710)] │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ TIME (LOCAL)  │ SEV  │ SOURCE      │ EVENT KIND      │ EVENT PAYLOAD SUMMARY                     │
├───────────────┼──────┼─────────────┼─────────────────┼───────────────────────────────────────────┤
│ 14:34:10.042  │ INFO │ Claude-3-7  │ tool.exec       │ git diff --stat (exit 0)                  │
│ 14:34:08.891  │ WARN │ Hermes      │ quota.warn      │ Claude token limit reached 85% threshold  │
│ 14:34:02.114  │ ERR  │ Codex-5     │ tool.timeout    │ vitest timed out after 30000ms            │
│ 14:33:55.780  │ OK   │ Agent-Reg   │ agent.started   │ Process spawned on OpenRig Seat #02       │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

#### Layout & Structural Recommendations
- **Sticky Codex Filter Strip**: Horizontal bar with filter chips for each active agent, plus dedicated chips for `Errors` and `Tools`. Each chip contains an active count badge.
- **Tabular Ledger Layout**: Clean alternating rows with fixed-width columns:
  - *Timestamp*: `font-variant-numeric: tabular-nums` in muted grey.
  - *Severity Pip*: 6px luminous dot (Green = OK, Amber = Warn, Red = Error).
  - *Source Chip*: Tagged with agent's semantic accent color.
  - *Event Kind*: Stylized monospace badge (`tool.exec`, `agent.started`).
  - *Payload Summary*: High-readability text with highlighted parameters.
- **Right-Side Event Inspector Drawer**: Clicking any row slides in a detailed JSON payload viewer with syntax highlighting and copy-to-clipboard functionality.

---

### 5.5 Usage Page (`/usage`): Stamina Meters & Resource Fuel Gauges

The `/usage` page monitors provider quotas, context windows, and token burn rates. This directly mirrors HoYoverse **Stamina / Resin / Fuel Management Systems**.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ RESOURCE TELEMETRY · PROVIDER QUOTAS & FUEL GAUGES                           STATUS: [OPTIMAL]   │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌─ 1 · DAILY TOKEN STAMINA ───┐ ┌─ 2 · WEEKLY OPERATOR BUDGET ┐ ┌─ 3 · PROVIDER QUOTA CEILINGS ┐ │
│ │                             │ │                             │ │ • ANTHROPIC CLAUDE          │ │
│ │          241.5k             │ │           1.84M             │ │   [███████████████░░░░] 74% │ │
│ │         ────────            │ │          ────────           │ │   Reset in: 04h 18m         │ │
│ │         500.0k              │ │           2.50M             │ │ • OPENAI CODEX              │ │
│ │      DAILY ALLOWANCE        │ │       WEEKLY CEILING        │ │   [██████░░░░░░░░░░░░░] 31% │ │
│ │                             │ │                             │ │   Reset in: 18h 02m         │ │
│ │ [████████████░░░░░░░░░] 48% │ │ [██████████████████░░░] 73% │ │ • GOOGLE AGY / GEMINI       │ │
│ │ Full recovery: 09h 25m      │ │ Burn Rate: ~42k tok/hour    │ │   [███████████████████] 96% │ │
│ └─────────────────────────────┘ └─────────────────────────────┘ └─────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ BUDGET RISK PROJECTIONS & MODEL FALLBACK SIMULATION                                              │
│ [!] AGY Gemini Weekly Quota at 96% — Auto-routing exploration tasks to Claude 3.5 Haiku          │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

#### Layout & Structural Recommendations
- **Trio of Hero Stamina Gauges**: Three prominent cards modeled after HSR's Trailblaze Power or Genshin's Condensed Resin display:
  - *Card 1: Daily Token Allowance* (Circular SVG gauge or segmented radial ring showing current consumption vs limit).
  - *Card 2: Weekly Enterprise Budget* (Projected exhaustion date with burn rate indicator).
  - *Card 3: Provider API Limits* (Anthropic, OpenAI, Google) with live countdown timers until rate-limit reset.
- **Model Fallback Routing Table**: Visual flowchart showing automatic routing logic when an agent hits quota limits.

---

## 6. Proposed Design Token Set (Tailwind CSS 4 & CSS Custom Properties)

These tokens translate the aesthetic principles into production-ready CSS custom properties for [LysControl](file:///home/lystiger/Projects/LysControl/src/styles/globals.css).

```css
@import "tailwindcss";

@layer base {
  :root {
    /* ------------------------------------------------------------------------
     * 1. SURFACE & BACKGROUND TOKENS (Deep Cosmic Obsidian & Acrylic Glass)
     * ------------------------------------------------------------------------ */
    --lys-bg-base: #08090B;               /* Deepest void canvas */
    --lys-surface-0: #0C0E12;             /* Base container / sidebar */
    --lys-surface-1: #12151B;             /* Standard card surface */
    --lys-surface-2: #181D25;             /* Elevated card / modal surface */
    --lys-surface-glass: rgba(18, 21, 27, 0.72); /* Glassmorphic acrylic */
    --lys-surface-interactive: #202632;    /* Hover / active control surface */

    /* ------------------------------------------------------------------------
     * 2. BORDER & STRUCTURAL TOKENS (Hairline Framing & Chamfers)
     * ------------------------------------------------------------------------ */
    --lys-border-subtle: #1C222C;          /* Muted partition hairline */
    --lys-border-default: #28303E;         /* Standard card border */
    --lys-border-highlight: #3D485C;       /* Focus / selected border */
    --lys-border-gold: #CBA35C;            /* Astral sovereign accent border */

    /* ------------------------------------------------------------------------
     * 3. AGENT ACCENT TOKENS (Role & Provider Chromatic Coding)
     * ------------------------------------------------------------------------ */
    --lys-agent-claude: #D9A05B;           /* Warm Terracotta / Astral Amber */
    --lys-agent-claude-glow: rgba(217, 160, 91, 0.18);
    
    --lys-agent-codex: #4EC9A0;            /* Cyber Mint / Jade Terminal */
    --lys-agent-codex-glow: rgba(78, 201, 160, 0.18);
    
    --lys-agent-agy: #5B8CFF;              /* Electric Cosmic Blue / Gemini */
    --lys-agent-agy-glow: rgba(91, 140, 255, 0.18);
    
    --lys-agent-hermes: #CBA35C;           /* Astral Sovereign Gold / Runtime */
    --lys-agent-hermes-glow: rgba(203, 163, 92, 0.20);

    /* ------------------------------------------------------------------------
     * 4. SEMANTIC STATUS & PRIORITY TOKENS
     * ------------------------------------------------------------------------ */
    --lys-status-success: #3FB950;         /* Execution completed / Optimal */
    --lys-status-warning: #E3A008;         /* Quota threshold / P1 Priority */
    --lys-status-danger: #F2555A;          /* Process failed / P0 Critical */
    --lys-status-info: #58A6FF;            /* Informational / Dispatched */
    --lys-status-idle: #8C949F;            /* Standby / Queued */

    /* ------------------------------------------------------------------------
     * 5. TYPOGRAPHY SCALES & METRICS
     * ------------------------------------------------------------------------ */
    --lys-font-display: 'Outfit', 'Space Grotesk', system-ui, sans-serif;
    --lys-font-body: 'Plus Jakarta Sans', 'Inter', -apple-system, sans-serif;
    --lys-font-mono: 'JetBrains Mono', ui-monospace, monospace;

    /* ------------------------------------------------------------------------
     * 6. MOTION TOKENS (Durations & Bespoke HoYoverse Curves)
     * ------------------------------------------------------------------------ */
    --lys-duration-instant: 100ms;         /* Micro-pops, clicks */
    --lys-duration-fast: 160ms;            /* Hovers, tab indicator slide */
    --lys-duration-normal: 260ms;          /* Panel unfolds, card reveals */
    --lys-duration-deliberate: 360ms;      /* Modal backdrops, drawer entry */

    /* Easing: HSR Smooth-Glide (High initial speed, elegant long deceleration) */
    --lys-ease-hsr: cubic-bezier(0.16, 1.0, 0.3, 1.0);
    
    /* Easing: ZZZ Kinetic-Snap (Snappy mechanical pop with controlled settle) */
    --lys-ease-zzz: cubic-bezier(0.34, 1.25, 0.64, 1.0);
    
    /* Easing: Standard Material Smooth */
    --lys-ease-standard: cubic-bezier(0.4, 0.0, 0.2, 1.0);

    /* ------------------------------------------------------------------------
     * 7. GEOMETRIC SHAPES & ELEVATION
     * ------------------------------------------------------------------------ */
    --lys-radius-sm: 2px;
    --lys-radius-md: 4px;
    --lys-radius-lg: 6px;
    --lys-clip-chamfer: polygon(0 0, calc(100% - 10px) 0, 100% 10px, 100% 100%, 10px 100%, 0 calc(100% - 10px));
    
    --lys-shadow-card: 0 4px 16px rgba(0, 0, 0, 0.45);
    --lys-shadow-elevated: 0 8px 32px rgba(0, 0, 0, 0.65);
    --lys-shadow-zzz-tactile: 0 3px 0 #181D25;
  }
}

/* ----------------------------------------------------------------------------
 * UTILITY CLASSES & REDUCED MOTION SAFEGUARDS
 * ---------------------------------------------------------------------------- */
.font-tabular {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum" 1;
}

.surface-glass {
  background: var(--lys-surface-glass);
  backdrop-filter: blur(12px) saturate(130%);
  -webkit-backdrop-filter: blur(12px) saturate(130%);
}

.clip-chamfer {
  clip-path: var(--lys-clip-chamfer);
}

/* Strict Accessibility Fallback */
@media (prefers-reduced-motion: reduce) {
  *, ::before, ::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

---

## 7. Accessibility & Ergonomics Standards

Implementing gaming-inspired design within an engineering operator console requires uncompromised adherence to enterprise accessibility standards.

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        ACCESSIBILITY COMPLIANCE                        │
│                                                                        │
│   WCAG 2.1 AA CONTRAST       KEYBOARD FOCUS           ARIA REAL-TIME   │
│   ────────────────────       ──────────────           ──────────────   │
│   • 4.5:1 text on glass      • 2px gold focus ring    • aria-live for  │
│   • 3:1 graphical icons      • Tab / Arrow navigation   SSE telemetry  │
│   • Redundant color markers  • Esc dismisses sheets   • Tabular labels │
└────────────────────────────────────────────────────────────────────────┘
```

1. **WCAG 2.1 AA Contrast Ratios on Translucent Glass**:
   - Translucent glass surfaces (`--lys-surface-glass`) can suffer contrast loss when layered over dynamic background content.
   - *Requirement*: Text foreground tokens (`--text-primary: #E6E9ED`) must maintain a minimum contrast ratio of **7.2:1** against `--lys-surface-1`, and at least **5.1:1** when layered over a worst-case translucent background blur.
   - *Rule*: Never rely solely on color to convey state. A status badge must pair its chromatic dot with an explicit textual label (`[● RUNNING]`, `[▲ WARN]`, `[✖ FAILED]`).

2. **Full Keyboard Focus Rings & Ergonomics**:
   - Every interactive element (tabs, cards, action buttons, timeline entries) must expose a distinct focus ring:
     ```css
     :focus-visible {
       outline: 2px solid var(--lys-border-gold);
       outline-offset: 2px;
     }
     ```
   - Provide standard keyboard navigation:
     - `1`, `2`, `3`: Instant switch between active agents.
     - `j` / `k`: Step forward/backward through the event stream or job queue.
     - `Escape`: Instantly closes any open modal drawer, returning focus to the triggering element.

3. **Screen Reader Optimization & ARIA Live Regions**:
   - The live SSE event stream (`GET /events/stream`) must not fire continuous disruptive announcements to screen readers.
   - *Implementation*: Wrap the stream container in `role="log"` with `aria-live="polite"` and `aria-relevant="additions text"`.
   - Ensure numerical stamina and quota bars declare `role="progressbar"`, `aria-valuenow`, `aria-valuemin="0"`, and `aria-valuemax`.

---

## 8. References & Design Citations

1. **HoYoverse Official Design & Developer Publications**:
   - HoYoverse Tech Blog: *[Designing Cross-Platform Multi-Resolution UIs in Unity](https://www.hoyoverse.com/)* (Cross-platform screen scaling and layout anchors).
   - miHoYo GDC Presentation: *[Evolving UI Frameworks from Honkai Impact 3rd to Genshin Impact](https://www.gdcvault.com/)* (Performance optimization for deep hierarchical menus).
2. **Game UI & UX Architectural Analyses**:
   - Game UI Database: *[Honkai: Star Rail UI Screen Breakdowns](https://www.gameuidatabase.com/game.php?id=1214)* (Inspection of roster rails, relic matrices, and trace trees).
   - Game UI Database: *[Zenless Zone Zero Urban Aesthetic UI Patterns](https://www.gameuidatabase.com/game.php?id=1285)* (Tactile CRT, halftone motifs, and chamfered surfaces).
   - ArtStation Design Studies: *[Zenless Zone Zero UI Concept & Layout Breakdown](https://www.artstation.com/search?sort_by=relevance&query=Zenless%20Zone%20Zero%20UI)* (Kinetic animation and graphic design packaging).
3. **Enterprise Telemetry & Ergonomics Research**:
   - Nielsen Norman Group: *[Dashboards: Making High-Density Data Scannable](https://www.nngroup.com/articles/dashboards-preattentive-attributes/)* (Guidelines for pre-attentive color attributes and spatial landmarks).
   - W3C Web Accessibility Initiative: *[WCAG 2.1 Non-Text Contrast & Reduced Motion Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)*.
4. **Freely Licensed Typography**:
   - [Plus Jakarta Sans](https://fonts.google.com/specimen/Plus+Jakarta+Sans) (Modern geometric-humanist sans by Tokotype, SIL Open Font License).
   - [Space Grotesk](https://fonts.google.com/specimen/Space+Grotesk) (Tactile tech display typeface by Florian Karsten, SIL Open Font License).
   - [JetBrains Mono](https://www.jetbrains.com/lp/mono/) (Developer monospace with tabular figures and programming ligatures, Apache 2.0).
