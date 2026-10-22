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

## 🚦 Integration Status

### 🟢 REAL INTEGRATION
- **Runtime Health (`GET /health`)**: Live Hermes status, process uptime, and version metadata.
- **Dynamic Agent Registry (`GET /agents`)**: Reads the live Hermes agent registry (`Antigravity/Gemini`, `Claude`, `Codex`, and dynamic agents).
- **Runtime Event History (`GET /events`)** and **Live Event Stream (`GET /events/stream` via SSE)**: stable event ids, `after=<event-id>` cursors, clean reconnects. The event taxonomy (`src/features/events/eventKinds.ts`) and the mock fixtures use the kinds Hermes emits.
- **Jobs (`GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`)**: job list, detail, tasks, runs, observations and token telemetry.
- **Execution (`GET /execution` + `execution.*` events)**: backend strip, resource cards and the execution timeline on `/execution`, with job task badges.
- **REST/SSE API Adapter**: `VITE_LYSSTACK_API_URL` is retained as an intentional compatibility configuration key and points to Hermes. If unavailable, LysControl shows a `disconnected` state rather than hiding failures behind mocks.

### 🧭 Roles and the run timeline
- **Roles belong to phases, not agents.** A sprint spec gives each phase a role (builder, hardener, verifier, security, ...); any agent can play any role, and one agent may run several phases. The console never labels an agent with a fixed role.
- **Run timeline**: every phase of a job on one time axis, start to finish, labelled with its role, the bar showing the agent that ran it. Phases of a `parallel_group` overlap. Shown on the Overview for every active job and in job detail. Source: `GET /jobs/{id}` phases (`order`, `role`, `agentId`, `startedAt`, `completedAt`), refetched on every `phase.*`, `job.*` and `task.*` event.
- **Running now · by role**: the Agents page lists each running phase across all active jobs (role · agent · phase · job · elapsed).
- **Agent status** follows the same rules as Hermes `GET /agents`: `phase.started` and `agent.started` set RUNNING, an agent in several parallel phases stays RUNNING until all finish, `phase.failed`, `agent.failed` and `agent.timed_out` set ERROR, `agent.cancelled` sets IDLE.

### 🟡 NOT REPORTED BY HERMES YET
- **Provider Quotas & Burn Telemetry**: quota meters and projection estimations are shown as unknown.
- **Time estimates**: no estimator for phase or job completion.

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
npm run test       # Vitest unit & architectural isolation suite (38 files, 291 tests)
npm run build      # Vite production bundle build

# Backend checks (hermes-lab)
cd /home/lystiger/Projects/Hermes-lab
pytest             # 927 passed, 7 skipped
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
│   │   ├── jobs/                  # Run timeline, queue tables, active execution cards
│   │   ├── messaging/             # Command dispatcher & tactical messaging
│   │   ├── execution/             # D-009 Execution page: backend strip, resource cards, timeline, job task badges
│   │   └── telemetry/             # Top metrics, quota lists, risk alerts
│   ├── routes/                    # Overview, Queue, Agents, AgentDetail, Usage, Events, Execution, Settings
│   ├── stores/                    # Zustand UI store (useConsoleStore), execution store + pure reducer (useExecutionStore, executionReducer)
│   └── styles/                    # Cybernetic theme CSS
├── public/agents/                 # Web-optimized WebP avatar crops & character cards
└── archive/design-reference/      # Archived: reference cards & prototype snapshots (not built)
```
