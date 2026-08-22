# LysControl

<div align="center">

**Tactical AI Agent Orchestration & Telemetry Command Station**

[![React](https://img.shields.io/badge/React-19.2-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-6.0+-646CFF?style=flat-square&logo=vite&logoColor=white)](https://vitejs.dev/)
[![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-4.0-38B2AC?style=flat-square&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![License](https://img.shields.io/badge/License-ISC-CBA35C?style=flat-square)](LICENSE)

</div>

---

## ⚡ Overview

**LysControl** is a cybernetic mission control console designed to orchestrate, monitor, and dispatch autonomous AI agent pipelines. It provides real-time telemetry, multi-agent execution graphs, token consumption budgets, provider rate-limit tracking, and interactive command dispatching across local container sandboxes and external LLM APIs.

---

## 🚀 Key Features

- **⚡ Real-Time Telemetry & Overview**:
  - Live metric stream tracking active jobs, queue depth, blocked tasks, today's token consumption, and projected spend.
  - Multi-layered 3D ambient gyro animations reflecting live pipeline execution.

- **🤖 Operator Registry & 3D Agent Cards**:
  - Registered AI operatives:
    - **Gemini** (`antigravity-2.5-pro`): Build, scaffolding, and database migrations.
    - **Claude** (`claude-sonnet-4-5`): Architecture, contract review, hardening, and documentation.
    - **Codex** (`gpt-5-codex`): Verification, test suites, static analysis, and regression audits.
    - **Elysia** (`lys-tactical-orchestrator`): Autonomous pipeline arbitration, handoffs, and dispatch.
  - Visual cards with animated WebP avatars, cyberpunk sigil fallbacks, breathing animations, code crawling backgrounds, and neon laser scanlines.
  - Detailed context window allocation gauges breaking down **Input**, **Output**, **Cached**, and **Remaining Free** tokens.

- **⛓️ Execution Pipeline & Priority Queue**:
  - Isometric connected diamond graph visualizer for `BUILD` → `HARDEN` → `VERIFY` → `COMPLETE` stages.
  - Priority-based job queue (`P0` critical to `P3` background) with repository locks, multi-agent chain badges, and token/time estimates.

- **🔍 Interactive Job Inspector**:
  - Full-screen modal inspector for any active or past job.
  - Granular changed files diff table (`+add` / `−del`), test runner log capture (pytest/ruff/mypy), sandbox retry histories, and structured tool call logs.

- **📊 Token Budget & Provider Quota Tracking**:
  - Real-time sprint budget burn meter with configurable hard-stop pause policies.
  - Provider rate limit tracking: Anthropic 5-hour rolling windows, OpenAI weekly plan allowances, Google AI Studio ledger quotas, and Herdr unmetered local container runtimes.
  - Predictive queue exhaustion models forecasting remaining budget after pending jobs.

- **📡 Live Audit Trace Stream**:
  - Sticky-header live event log streaming timestamps, sources, event kinds, durations, and targets.
  - Filterable by agent, tool invocations, or error/retry warnings.

- **🕹️ Tactical Command Dispatcher**:
  - Interactive command console to inject prompts, retry failed jobs, trigger manual handoffs, or query agent states directly.

---

## 📁 Architecture & File Structure

```
LysControl/
├── src/
│   ├── routes/
│   │   ├── index.tsx                 # Overview dashboard & telemetry
│   │   ├── queue.tsx                 # Execution pipeline & priority queue
│   │   ├── agents/
│   │   │   ├── index.tsx             # Operator registry grid
│   │   │   └── $agentId.tsx          # Operator detail (3D portrait, context, metrics)
│   │   ├── usage.tsx                 # Token budgets, context windows & quotas
│   │   ├── events.tsx                # Real-time streaming audit trace logs
│   │   └── settings.tsx              # Runtime environment, policy & sandbox
│   │
│   ├── components/
│   │   ├── Layout.tsx                # Shell with Sidebar, Header & JobModal
│   │   ├── Sidebar.tsx               # Navigation with daemon health status
│   │   ├── Header.tsx                # Dynamic breadcrumbs & live latency ETA
│   │   ├── JobModal.tsx              # Floating Job Inspector modal
│   │   ├── AnimatedCube.tsx          # 3D spinning gold cube logo
│   │   ├── AmbientGyro.tsx           # Multi-layered 3D rotating rings
│   │   ├── Badge.tsx                 # Cyber status / priority badges
│   │   └── CyberButton.tsx           # Action buttons
│   │
│   ├── features/
│   │   ├── agents/                   # Agent cards, meters, metrics & portraits
│   │   ├── jobs/                     # Pipeline graphs, queue tables & diff views
│   │   ├── messaging/                # Inter-agent chatter & command dispatchers
│   │   ├── telemetry/                # Top metrics bar, quotas & budget alerts
│   │   └── tools/                    # Tool execution items & Docker sandbox status
│   │
│   ├── api/
│   │   ├── types.ts                  # TypeScript interfaces & domain contracts
│   │   ├── mockData.ts               # Agent profiles, jobs, pipelines & seeds
│   │   └── client.ts                 # API client with dispatch & event stream
│   │
│   ├── stores/
│   │   └── useConsoleStore.ts        # Global state, live clock & event stream
│   │
│   └── styles/
│       └── globals.css               # Tailwind CSS, cyber scanlines & 3D keyframes
│
└── public/
    └── agents/                       # Cyberpunk operator portraits (.webp)
```

---

## 🛠️ Getting Started

### Prerequisites

- **Node.js**: `v20.0.0` or higher
- **npm**, **pnpm**, or **yarn**

### Installation

```bash
# Clone the repository
git clone https://github.com/lystiger/LysControl.git
cd LysControl

# Install dependencies
npm install
```

### Development Server

Start the local development server on `http://localhost:3000`:

```bash
npm run dev
```

### Production Build

Compile the optimized production bundle into `dist/`:

```bash
npm run build
```

Preview the production build locally:

```bash
npm run preview
```

---

## ⚙️ Configuration

LysControl reads local daemon and operator configurations from:

- `~/.lyscontrol/config.toml`: Runtime daemons, Redis state stores, retention policies, and hard-stop token caps.
- `~/.lyscontrol/agents.toml`: Operator registration, concurrency bounds, model providers, and system directives.

---

## 📜 License

This project is licensed under the **ISC License**.
