# LysControl

<div align="center">

**Operator Console for the Hermes Runtime**

[![React](https://img.shields.io/badge/React-19.2-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-8.2-646CFF?style=flat-square&logo=vite&logoColor=white)](https://vitejs.dev/)
[![Zustand](https://img.shields.io/badge/Zustand-5.0-brown?style=flat-square)](https://github.com/pmndrs/zustand)
[![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-4.3-38B2AC?style=flat-square&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![CI](https://github.com/lystiger/LysControl/actions/workflows/ci.yml/badge.svg)](https://github.com/lystiger/LysControl/actions/workflows/ci.yml)

</div>

---

## ⚡ Overview

**LysControl** is the operator-facing UI for visualizing and monitoring engineering jobs owned by the **Hermes Runtime**. Operators can submit control requests through Hermes REST APIs; Hermes owns scheduling and agent execution.

> [!NOTE]
> **Architectural Boundary**: LysControl is a frontend for visualization, telemetry, and operator controls. It does not execute agents or own canonical job/task state. It communicates with Hermes through REST/SSE. `VITE_LYSSTACK_API_URL` remains as an intentional compatibility environment variable.

```text
                     USER
                       │
                       ▼
                  LysControl
               React + Vite UI
                       │
                       │ HTTP + SSE
                       ▼
             Existing API adapter
                       │
                       ▼
              Hermes Runtime REST API (FastAPI)
                       │
          ┌────────────┼────────────┐
          │            │            │
          ▼            ▼            ▼
       Gemini        Claude        Codex
          │
          └──── Hermes Runtime / Worktrees
```

---

## 🚦 Integration Status (Phase 3)

### 🟢 REAL INTEGRATION
- **Runtime Health (`GET /health`)**: Live Hermes status, process uptime, and version metadata.
- **Dynamic Agent Registry (`GET /agents`)**: Reads the live Hermes agent registry (`Antigravity/Gemini`, `Claude`, `Codex`, and dynamic agents).
- **Runtime Event History (`GET /events`)**: Historical event log retrieval supporting limits and `after=<event-id>` cursor pagination.
- **Live Event Stream (`GET /events/stream` via SSE)**: Real-time Server-Sent Events delivery for `runtime.started`, `agent.started`, `agent.finished`, `agent.failed`, and tool execution traces with stable event IDs and clean disconnect handling.
- **REST/SSE API Adapter**: `VITE_LYSSTACK_API_URL` is retained as an intentional compatibility configuration key and points to Hermes. If unavailable, LysControl shows a `disconnected` state rather than hiding failures behind mocks.
- **Connection Indicator**: Header connection indicator reflects live network state (`connected`, `connecting`, `disconnected`, `mock mode`).

### 🟣 EXECUTION PAGE (D-009, Phase B: frontend built against the contract)
- **Execution route (`/execution`)**: backend status strip (subprocess, herdr, openrig daemon and ledger), live resource cards grouped by backend (state, job/task, reused badge, generation, pooled-seat expiry countdown, failed resources highlighted in red), and a recent `execution.*` timeline.
- **Snapshot + events**: loads `GET /execution` (`getExecutionSnapshot`) on start and again after an SSE reconnect. `execution.*` events from the existing stream are applied on top. Events received while a snapshot is in flight are buffered and replayed. Duplicate event ids are ignored and stale per-resource events (older `rawTs`) are dropped.
- **Job detail**: each task's backend and resource badge (grouped by `taskId` from execution events), linking to the Execution page.
- **Settings / Sidebar**: the static "Herdr sandbox" panel is removed. The Sidebar Herdr status and the Settings backend list now come from the execution snapshot.
- **Status**: frontend complete and covered by mock-backed tests. Real data depends on Hermes Phase A (`GET /execution` and the `execution.*` event kinds). Until that lands, mock mode shows fixtures with a "MOCK FIXTURES" banner.

### 🟡 SIMULATED TEMPORARILY (Transitioning in Phase 4)
- **Jobs & Queue Lifecycle**: Job details, execution graph mutations, and retry triggers.
- **Provider Quotas & Burn Telemetry**: Quota meters and projection estimations.
- **Command Dispatcher Mutation**: Operator command execution pipeline.

---

## 🛠️ Local Development & Quick Start

### 1. Start the Hermes Runtime API (`Hermes-lab`)

```bash
cd /home/lystiger/Projects/Hermes-lab
source .venv/bin/activate
uvicorn main:app --port 8000 --reload
```

The Hermes Runtime API will be available at `http://localhost:8000`:
- Health check: `http://localhost:8000/health`
- Agent registry: `http://localhost:8000/agents`
- Event history: `http://localhost:8000/events`
- Event stream: `http://localhost:8000/events/stream`

### 2. Start the LysControl Frontend

```bash
cd /home/lystiger/Projects/LysControl

# Connect LysControl to the Hermes Runtime API
VITE_LYSSTACK_API_URL=http://localhost:8000 npm run dev

# Or run in standalone mock mode (no backend required)
npm run dev
```

Open `http://localhost:3000` (or Vite's output port) to access the console.

---

## 🧪 Testing & Verification

```bash
# Frontend checks (LysControl)
npm run typecheck  # TypeScript compiler validation (0 errors)
npm run lint       # ESLint flat config inspection (0 errors)
npm run test       # Vitest unit & architectural isolation suite (14 suites, 62 tests)
npm run build      # Vite production bundle build

# Backend checks (hermes-lab)
cd /home/lystiger/Projects/Hermes-lab
pytest             # 109 passed, 2 skipped
```

---

## 🏛️ Repository Architecture

```text
LysControl/
├── src/
│   ├── api/
│   │   ├── contracts.ts           # Hermes API contract & EventSubscription
│   │   ├── types.ts               # Domain models (AgentSummary, TraceEvent, HealthStatus)
│   │   ├── actors.ts              # Domain actor presentation resolver (registry -> system -> fallback)
│   │   ├── client.ts              # Pluggable API client factory (HTTP vs Mock adapter)
│   │   ├── hooks.ts               # React hooks (useHealth, useAgents, useEventStream, useJobs, useExecution)
│   │   ├── adapters/
│   │   │   ├── httpAdapter.ts     # Hermes REST + SSE adapter (legacy class name)
│   │   │   └── mockAdapter.ts     # Standalone offline mock adapter
│   │   └── mock/                  # Pure mock fixtures (isolated behind mockAdapter; execution.ts for D-009)
│   ├── components/                # Layout, Sidebar, Header, JobModal, DossierModal
│   ├── features/
│   │   ├── agents/                # Agent portraits, meters, activity, metrics grids
│   │   ├── jobs/                  # Execution graph, queue tables, active execution cards
│   │   ├── messaging/             # Command dispatcher & tactical messaging
│   │   ├── execution/             # D-009 Execution page: backend strip, resource cards, timeline, job task badges
│   │   └── telemetry/             # Top metrics, quota lists, risk alerts
│   ├── routes/                    # Overview, Queue, Agents, AgentDetail, Usage, Events, Execution, Settings
│   ├── stores/                    # Zustand UI store (useConsoleStore), execution store + pure reducer (useExecutionStore, executionReducer)
│   └── styles/                    # Cybernetic theme CSS
├── public/agents/                 # Web-optimized WebP avatar crops & character cards
└── design-reference/              # Reference cards & prototype snapshots
```
