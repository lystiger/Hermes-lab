"""Tools for the orchestrator, served over MCP (stdio). Read-only except for saving a draft.

The orchestrator can read LysStack, read Hermes job and capacity status, and save a brief
draft into LysStack/drafts/ as Draft. It cannot start, cancel, or merge a run, and it has
no shell or file-edit tools. The Claude CLI is started with --strict-mcp-config, so only
the tools in this file are available.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from orchestrator.chat import TOOL_NAMES, ChatError, ConversationStore, write_drafts

PROTOCOL_VERSION = "2024-11-05"
MAX_READ_BYTES = 64 * 1024
LIST_SCOPES = {"docs": "docs", "operating_system": "operating_system", "projects": "projects", "memory": "memory"}
HERMES_API = "http://localhost:8000"

TOOLS = [
    {
        "name": "lysstack_list",
        "description": "List LysStack files in one folder: docs, operating_system, projects, or memory. Read-only.",
        "inputSchema": {
            "type": "object",
            "properties": {"scope": {"type": "string", "enum": sorted(LIST_SCOPES)}},
            "required": ["scope"],
            "additionalProperties": False,
        },
    },
    {
        "name": "lysstack_read",
        "description": "Read one LysStack file by its path relative to the LysStack root. Read-only, up to 64 KB.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "hermes_jobs",
        "description": "List Hermes jobs with their status. Read-only.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "hermes_capacity",
        "description": "Show provider quota: how much of each agent's window is used. Read-only.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "usage_analysis",
        "description": "Plan a long session: each agent's quota left, each chat's context use, and plain "
                       "recommendations. Read-only.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "agent_options",
        "description": "List each agent with its allowed models, reasoning levels, readiness and quota left. "
                       "Use this before suggesting agents for a brief. Read-only.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "draft_save",
        "description": "Save a brief draft into LysStack/drafts/. The status is forced to Draft. Never starts a run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "lowercase letters, digits and hyphens, ending in .md"},
                "body": {"type": "string", "description": "the full brief in LysStack active_task format"},
            },
            "required": ["name", "body"],
            "additionalProperties": False,
        },
    },
]


class ToolError(Exception):
    """A tool call cannot be served. Reported to the model as an error result."""


class LysStackTools:
    def __init__(self, lysstack_root, drafts_dir=None, api=HERMES_API, state_dir=None):
        self.root = Path(lysstack_root).resolve()
        self.drafts_dir = Path(drafts_dir) if drafts_dir else self.root / "drafts"
        self.api = api
        self.state_dir = Path(state_dir) if state_dir else None

    def _inside_root(self, relative):
        target = (self.root / relative).resolve()
        if self.root not in target.parents and target != self.root:
            raise ToolError("path is outside LysStack")
        if ".git" in target.relative_to(self.root).parts:
            raise ToolError("git internals are not readable")
        return target

    def lysstack_list(self, scope):
        folder = LIST_SCOPES.get(scope)
        if folder is None:
            raise ToolError(f"scope must be one of {', '.join(sorted(LIST_SCOPES))}")
        base = self.root / folder
        if not base.is_dir():
            return []
        return sorted(str(p.relative_to(self.root)) for p in base.rglob("*") if p.is_file())

    def lysstack_read(self, path):
        target = self._inside_root(path)
        if not target.is_file():
            raise ToolError("no such file in LysStack")
        data = target.read_bytes()
        truncated = len(data) > MAX_READ_BYTES
        text = data[:MAX_READ_BYTES].decode("utf-8", errors="replace")
        return text + ("\n[truncated at 64 KB]" if truncated else "")

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.api + path, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ToolError(f"Hermes API unavailable: {exc}") from exc

    def hermes_jobs(self):
        jobs = self._get("/jobs")
        rows = jobs if isinstance(jobs, list) else jobs.get("jobs", [])
        return [{"id": j.get("id") or j.get("jobId"), "status": j.get("status"), "sprint": j.get("sprintId")} for j in rows]

    def hermes_capacity(self):
        return self._get("/capacity/limits")

    def _quota(self):
        """Per-agent quota as Hermes reports it. Empty when Hermes is down."""
        try:
            rows = self._get("/capacity/limits").get("agents", [])
        except ToolError:
            return {}
        return {row["id"]: row for row in rows if isinstance(row, dict) and "id" in row}

    def usage_analysis(self):
        quota = self._quota()
        chats = ConversationStore(self.state_dir).list() if self.state_dir else []
        return analyze_usage(quota, chats)

    def agent_options(self):
        quota = self._quota()
        try:
            models = self._get("/agents/models")
        except ToolError:
            models = {}
        rows = []
        for agent_id in sorted(set(models) | set(quota)):
            config = models.get(agent_id, {})
            q = quota.get(agent_id, {})
            rows.append({
                "id": agent_id,
                "allowed": config.get("allowed", []),
                "configured": config.get("configured"),
                "ready": q.get("ready"),
                "status": q.get("status"),
                "leftPct": q.get("leftPct"),
                "resetsAt": q.get("resetsAt"),
            })
        return rows

    def draft_save(self, name, body):
        try:
            written = write_drafts(f"```brief-draft path={name}\n{body}\n```", self.drafts_dir)
        except ChatError as exc:
            raise ToolError(str(exc)) from exc
        return {"saved": written, "status": "Draft"}


LOW_QUOTA_PCT = 20
WARN_CONTEXT_PCT = 60
HIGH_CONTEXT_PCT = 85


def analyze_usage(quota, chats):
    """Plain facts and rules for planning a session. Deterministic, so the model only explains it."""
    agents = []
    recommendations = []
    for agent_id in sorted(quota):
        q = quota[agent_id]
        left = q.get("leftPct")
        agents.append({"id": agent_id, "ready": q.get("ready"), "status": q.get("status"),
                       "leftPct": left, "resetsAt": q.get("resetsAt")})
        if q.get("ready") is False:
            recommendations.append(f"Avoid {agent_id} for new phases: it is not ready.")
        elif left is None:
            recommendations.append(f"{agent_id} quota is unknown; check it before assigning long phases.")
        elif left < LOW_QUOTA_PCT:
            recommendations.append(
                f"{agent_id} has {left}% left in its window; prefer other agents for long phases "
                f"until it resets at {q.get('resetsAt') or 'an unknown time'}.")
    chat_rows = []
    for chat in chats:
        usage = chat.get("usage") or {}
        window = usage.get("context_window")
        if not window:
            continue
        percent = min(100, round(usage.get("context_tokens", 0) / window * 100))
        chat_rows.append({"id": chat.get("id"), "title": chat.get("title"), "percent": percent,
                          "summarized": bool(chat.get("summary"))})
        if percent >= HIGH_CONTEXT_PCT:
            recommendations.append(f"Chat '{chat.get('title')}' is {percent}% full: compact it now.")
        elif percent >= WARN_CONTEXT_PCT:
            recommendations.append(f"Chat '{chat.get('title')}' is {percent}% full: compact it soon.")
    return {
        "agents": agents,
        "chats": chat_rows,
        "recommendations": recommendations or ["No action needed."],
    }


def _text_result(value, is_error=False):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def handle(message, tools):
    """Answer one JSON-RPC message. Returns the response, or None for notifications."""
    method = message.get("method")
    if "id" not in message:
        return None
    request_id = message["id"]
    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "lysstack", "version": "0.1.0"},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            if name == "lysstack_list":
                result = _text_result(tools.lysstack_list(args.get("scope", "")))
            elif name == "lysstack_read":
                result = _text_result(tools.lysstack_read(args.get("path", "")))
            elif name == "hermes_jobs":
                result = _text_result(tools.hermes_jobs())
            elif name == "hermes_capacity":
                result = _text_result(tools.hermes_capacity())
            elif name == "usage_analysis":
                result = _text_result(tools.usage_analysis())
            elif name == "agent_options":
                result = _text_result(tools.agent_options())
            elif name == "draft_save":
                result = _text_result(tools.draft_save(args.get("name", ""), args.get("body", "")))
            else:
                result = _text_result(f"unknown tool: {name}", is_error=True)
        except ToolError as exc:
            result = _text_result(str(exc), is_error=True)
    else:
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def serve(lysstack_root, drafts_dir=None, state_dir=None, stdin=sys.stdin, stdout=sys.stdout):
    tools = LysStackTools(lysstack_root, drafts_dir=drafts_dir, state_dir=state_dir)
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(message, tools)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description="LysStack tools for the orchestrator (MCP over stdio)")
    parser.add_argument("--root", required=True, type=Path, help="Path to the LysStack repository")
    parser.add_argument("--drafts", type=Path, default=None, help="Where draft_save writes (default: ROOT/drafts)")
    parser.add_argument("--state", type=Path, default=None, help="Orchestrator chat state folder, read by usage_analysis")
    args = parser.parse_args(argv)
    serve(args.root, drafts_dir=args.drafts, state_dir=args.state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
