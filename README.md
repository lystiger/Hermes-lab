# LysControl

<div align="center">

**Tactical AI Agent Orchestration & Telemetry Command Station**

[![React](https://img.shields.io/badge/React-19.2-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-8.2-646CFF?style=flat-square&logo=vite&logoColor=white)](https://vitejs.dev/)
[![Zustand](https://img.shields.io/badge/Zustand-5.0-brown?style=flat-square)](https://github.com/pmndrs/zustand)
[![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-4.3-38B2AC?style=flat-square&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![CI](https://img.shields.io/badge/CI-Passing-3FB950?style=flat-square)](https://github.com/lystiger/LysControl/actions)

</div>

---

## ⚡ Overview

**LysControl** is the operator-facing console designed to visualize, monitor, and dispatch autonomous AI agent pipelines orchestrated by the **LysStack** control plane. 

> [!NOTE]
> **Architectural Boundary**: LysControl is strictly a frontend visualization and operator console. It does not own server scheduling, container execution, or provider API connections. All data flows through the `LysStackApi` contract layer.

```text
LysControl (Console UI)
    │
    │  LysStackApi Contracts (REST + SSE / WS)
    ▼
LysStack Control Plane (Future Backend)
    ├── Agent Registry (Dynamic Operatives)
    ├── Job Scheduler & Queue
    ├── Telemetry & Token Quotas
    └── Container Sandboxes & Tool Adapters
```

---

## 🚦 Feature Status & Architecture

### 🟢 Implemented Frontend Architecture
- **Generic Agent Identity & Dynamic Operatives**: Closed agent unions removed. Any dynamic agent (e.g. `kimi`, `qwen`, or dynamic subagents like `reviewer-8f92`) is supported via generic `AgentId` and `AgentSummary` / `AgentDetail` domain models without modifying core frontend types.
- **Decoupled Presentation Metadata & Graceful Fallbacks**: Agent artwork is optional. Agents without WebP portraits automatically render cybernetic geometric sigils, initials glyphs, and accent borders.
- **Domain Separation of Actors**: AI agents, system daemons (`lyscontrol`, `lysstack`), runtimes (`hermes`, `herdr`), and tools (`pytest`) are modeled distinctly as `ActorRef`.
- **Global UI State Management**: Built on **Zustand** (`useConsoleStore`) for client preferences, 3D motion toggles, active modals, and streamed audit buffers.
- **Contract & API Layer**: `LysStackApi` interface with pluggable adapters (`MockLysStackApi`, ready for `HttpLysStackApi`). Routes and components consume data solely through hooks (`useAgents`, `useJobs`, `usePipeline`, `useTelemetry`).
- **Interactive Visual Console**:
  - **Overview (`/`)**: Real-time telemetry, 3D ambient gyros, agent lanes, and live event trace.
  - **Queue (`/queue`)**: Serial execution order graph and priority queue (`P0`–`P3`).
  - **Agents (`/agents` & `/agents/:agentId`)**: Tactical grid and deep inspection (3D portraits, multi-segment context breakdown, activity logs, allowance windows, and run histories).
  - **Usage (`/usage`)**: Token burn meters, provider rate-limit windows, and queue projections.
  - **Events (`/events`)**: Sticky-header filterable event audit log.
  - **Settings (`/settings`)**: Runtime daemon status, policy caps, and 3D client rendering controls.
  - **Job Inspector Modal**: Changed files diff table, test runner logs, retry history, and structured tool calls.

### 🟡 Simulated Currently (Mock Layer)
- **Telemetry & Clock Pulse**: Background ticker simulating token consumption burn and event arrivals.
- **Provider Quota Windows**: Static mock quotas for Anthropic (5h rolling), OpenAI (weekly plan), Google AI Studio (daily ledger), and Herdr local container.
- **Job Pipeline & Queue Data**: Pre-configured mock fixtures for active migration job `#142` and pending tasks.
- **Operator Command Dispatcher**: Local mock feedback acknowledging operator prompts.

### 🔵 Planned for Real LysStack Integration
- **Direct Control Plane Connection**: Replace `MockLysStackApi` with `HttpLysStackApi` via REST and SSE/WebSocket real-time feeds.
- **Live Tool & Sandbox Streaming**: Real Docker / containerd execution logs and interactive test runners.
- **A2A & MCP Messaging Adapters**: Multi-agent communication routing and MCP tool capabilities.
- **Persona Memory & Relationship Dialogue**: Autonomous character interaction layers after runtime contracts are established.

---

## 📁 Project Structure

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
│   │   ├── Header.tsx                # Dynamic breadcrumbs & live telemetry
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
│   │   ├── types.ts                  # Clean TypeScript domain contracts & types
│   │   ├── contracts.ts              # LysStackApi interface definition
│   │   ├── client.ts                 # API client singleton
│   │   ├── hooks.ts                  # React query & domain data hooks
│   │   ├── adapters/
│   │   │   └── mockAdapter.ts        # MockLysStackApi implementation
│   │   └── mock/
│   │       ├── actors.ts             # System actors & resolver functions
│   │       ├── agents.ts             # Agent mock datasets & dynamic generator
│   │       ├── jobs.ts               # Jobs, pipelines & diff fixtures
│   │       ├── telemetry.ts          # Quotas, projections & settings
│   │       └── events.ts             # Seed and pool event logs
│   │
│   ├── stores/
│   │   └── useConsoleStore.ts        # Zustand global store for client UI state
│   │
│   └── styles/
│       └── globals.css               # Tailwind CSS, cyber scanlines & 3D keyframes
│
├── public/
│   └── agents/                       # Cyberpunk operator portraits (.webp)
│
├── design-reference/                 # Preserved original design prototype assets
└── .github/workflows/ci.yml          # GitHub Actions CI pipeline
```

---

## 🛠️ Getting Started

### Prerequisites

- **Node.js**: `v20.0.0` or higher
- **npm**

### Installation

```bash
# Clone the repository
git clone https://github.com/lystiger/LysControl.git
cd LysControl

# Install dependencies
npm install
```

### Development Server

Start the local Vite dev server on `http://localhost:3000`:

```bash
npm run dev
```

### Quality & Engineering Commands

```bash
# Typecheck TypeScript codebase
npm run typecheck

# Lint with ESLint
npm run lint

# Run Vitest test suite
npm run test

# Build production bundle
npm run build

# Preview production build locally
npm run preview
```

---

## 📜 License

This project is licensed under the **ISC License**.
