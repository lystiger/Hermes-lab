"""Tools for the orchestrator, served over MCP (stdio). Read-only except for saving a draft.

The orchestrator can read LysStack, read Hermes job and capacity status, and save a brief
draft into LysStack/drafts/ as Draft. It cannot start, cancel, or merge a run, and it has
no shell or file-edit tools. The Claude CLI is started with --strict-mcp-config, so only
the tools in this file are available.
"""

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from agent_models import canonical
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
        "name": "brief_check",
        "description": "Check a saved draft before it is marked Ready: status, task id, goal, target repo, pinned "
                       "40-character baseline, acceptance criteria, verification, and that every context file exists. Read-only.",
        "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}},
                        "required": ["name"], "additionalProperties": False},
    },
    {
        "name": "brief_build",
        "description": "Assemble a brief in LysStack format from structured fields. Returns the text only; "
                       "save it with draft_save.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "goal": {"type": "string"},
                "repository": {"type": "string"},
                "baseline": {"type": "string", "description": "full 40-character commit SHA"},
                "context_files": {"type": "array", "items": {"type": "string"}},
                "acceptance": {"type": "array", "items": {"type": "string"}},
                "verification": {"type": "array", "items": {"type": "string"}},
                "non_goals": {"type": "array", "items": {"type": "string"}},
                "decisions": {"type": "array", "items": {"type": "string"},
                              "description": "settled answers, each with its source, e.g. 'Use FastAPI (Lystiger)'"},
            },
            "required": ["task_id", "goal", "repository", "baseline", "context_files", "acceptance", "verification"],
            "additionalProperties": False,
        },
    },
    {
        "name": "decision_search",
        "description": "Search the project decisions, lessons and memory for a word or phrase. Read-only.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}},
                        "required": ["query"], "additionalProperties": False},
    },
    {
        "name": "job_detail",
        "description": "Show one Hermes job: status, phase, agents, progress, and the reason it is blocked or failed. Read-only.",
        "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}},
                        "required": ["job_id"], "additionalProperties": False},
    },
    {
        "name": "repo_state",
        "description": "Check a product clone under ~/Projects: is it on the pinned baseline, is it clean, and is the "
                       "baseline present. Read-only.",
        "inputSchema": {"type": "object", "properties": {"repo": {"type": "string", "description": "folder name, e.g. Unigreen"}},
                        "required": ["repo"], "additionalProperties": False},
    },
    {
        "name": "list_drafts",
        "description": "List the drafts in LysStack/drafts with their status and task id. Read-only.",
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
        """Per-agent quota as Hermes reports it, keyed by canonical agent id. Empty when Hermes is down."""
        try:
            rows = self._get("/capacity/limits").get("agents", [])
        except ToolError:
            return {}
        merged = {}
        for row in rows:
            if isinstance(row, dict) and "id" in row:
                merged.setdefault(canonical(row["id"]), row)
        return merged

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
        configs = {}
        for agent_id, config in models.items():
            configs.setdefault(canonical(agent_id), config)
        rows = []
        for agent_id in sorted(set(configs) | set(quota)):
            config = configs.get(agent_id, {})
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

    def brief_check(self, name):
        target = self.drafts_dir / name if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,60}\.md", name or "") else None
        if target is None or not target.is_file():
            raise ToolError("no draft with that name")
        return check_brief(target.read_text(encoding="utf-8", errors="replace"), self.root)

    def brief_build(self, fields):
        return build_brief(fields)

    def decision_search(self, query):
        return search_knowledge(self.root, query)

    def job_detail(self, job_id):
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", job_id or ""):
            raise ToolError("job id has an unexpected form")
        job = self._get(f"/jobs/{job_id}")
        keys = ("id", "title", "status", "currentPhase", "assignedAgentIds", "progress", "blockedReason",
                "repairCount", "replanCount", "startedAt", "completedAt")
        return {k: job.get(k) for k in keys}

    def repo_state(self, repo):
        baseline = ""
        task = self.root / "operating_system" / "active_task.md"
        if task.is_file():
            match = re.search(r"\*\*Pinned baseline:\*\*\s*`([^`]+)`", task.read_text(encoding="utf-8", errors="replace"))
            baseline = match.group(1) if match else ""
        return repo_state_for(repo, baseline_from=baseline)

    def list_drafts(self):
        return list_draft_rows(self.drafts_dir)

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
        # quota keys are already canonical, so gemini, agy and antigravity are one agent
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


SHA = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_SECTIONS = ("Goal", "Target", "Bounded Context Files", "Acceptance Criteria", "Verification")


def check_brief(text, root):
    """Each check on a brief: a list of {check, ok, detail}. Pure apart from reading the context files."""
    checks = []

    def add(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    status = re.search(r"^- \*\*Status:\*\*\s*(.+)$", text, re.MULTILINE)
    add("status line", status is not None, status.group(1) if status else "missing")
    add("status is Draft", status and status.group(1).strip() == "Draft",
        "a draft is never Ready until Lystiger sets it")
    task = re.search(r"^- \*\*Task ID:\*\*\s*(\S+)", text, re.MULTILINE)
    add("task id", task is not None, task.group(1) if task else "missing")
    for section in REQUIRED_SECTIONS:
        add(f"section: {section}", re.search(rf"^## {re.escape(section)}\s*$", text, re.MULTILINE) is not None)
    baseline = re.search(r"\*\*Pinned baseline:\*\*\s*`([^`]+)`", text)
    add("pinned baseline is a full SHA", baseline and SHA.match(baseline.group(1)),
        baseline.group(1) if baseline else "missing")
    context = re.findall(r"^- `([^`]+)`", _section_text(text, "Bounded Context Files"), re.MULTILINE)
    add("context files listed", bool(context), f"{len(context)} listed")
    for name in context:
        add(f"context file exists: {name}", (Path(root) / name).is_file())
    criteria = re.findall(r"^\s*(?:-\s+\[[ xX]\]|-|\d+\.)\s+(.+)$", _section_text(text, "Acceptance Criteria"), re.MULTILINE)
    add("acceptance criteria", len(criteria) >= 1, f"{len(criteria)} criteria")
    commands = re.findall(r"^\s*(?:-|\d+\.)\s+.+$", _section_text(text, "Verification"), re.MULTILINE)
    add("verification commands", len(commands) >= 1, f"{len(commands)} commands")
    return checks


def _section_text(text, heading):
    match = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return match.group(1) if match else ""


def build_brief(fields):
    """A brief in LysStack format from structured fields. Refuses a baseline that is not a full SHA."""
    baseline = fields["baseline"].strip()
    if not SHA.match(baseline):
        raise ToolError("baseline must be a full 40-character commit SHA")
    if not fields["acceptance"] or not fields["verification"]:
        raise ToolError("a brief needs acceptance criteria and verification commands")
    lines = [
        "# Active Task", "",
        "## Assignment", "",
        f"- **Task ID:** {fields['task_id']}",
        "- **Status:** Draft",
        "", "## Goal", "", fields["goal"],
        "", "## Target", "",
        f"- **Repository:** `{fields['repository']}`",
        f"- **Pinned baseline:** `{baseline}`",
        "", "## Bounded Context Files", "",
    ]
    lines += [f"- `{name}`" for name in fields["context_files"]]
    lines += ["", "## Acceptance Criteria", ""]
    lines += [f"- [ ] {item}" for item in fields["acceptance"]]
    lines += ["", "## Verification", ""]
    lines += [f"- `{command}`" for command in fields["verification"]]
    if fields.get("non_goals"):
        lines += ["", "## Non-Goals", ""] + [f"- {item}" for item in fields["non_goals"]]
    if fields.get("decisions"):
        lines += ["", "## Decisions", ""] + [f"- {item}" for item in fields["decisions"]]
    return "\n".join(lines) + "\n"


def repo_state_for(name, projects=None, baseline_from=None):
    """Read-only git checks on a clone under ~/Projects. Refuses names that are not plain folder names."""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name or ""):
        raise ToolError("repo must be a plain folder name, such as Unigreen")
    base = Path(projects) if projects else Path.home() / "Projects"
    repo = base / name
    if not (repo / ".git").exists():
        raise ToolError(f"{name} is not a git clone under {base}")
    baseline = baseline_from or ""

    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)

    head = git("rev-parse", "HEAD").stdout.strip()
    status = git("status", "--porcelain").stdout
    present = git("cat-file", "-e", f"{baseline}^{{commit}}").returncode == 0 if baseline else False
    ahead = git("rev-list", "--count", f"{baseline}..HEAD").stdout.strip() if present else None
    return {
        "repo": name, "head": head, "baseline": baseline or None, "baseline_present": present,
        "on_baseline": bool(baseline) and head == baseline, "clean": status.strip() == "",
        "commits_after_baseline": int(ahead) if ahead and ahead.isdigit() else None,
    }


def search_knowledge(root, query):
    """Lines that mention the query in project decisions and lessons, memory, and the decision log."""
    needle = (query or "").strip().lower()
    if len(needle) < 2:
        raise ToolError("search for at least two characters")
    files = sorted(Path(root).glob("projects/*/decisions.md")) + sorted(Path(root).glob("projects/*/lessons.md"))
    files += sorted(Path(root).glob("memory/*.md")) + [Path(root) / "operating_system" / "decision-log.md"]
    hits = []
    for path in files:
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if needle in line.lower():
                hits.append({"file": str(path.relative_to(root)), "line": number, "text": line.strip()[:200]})
                if len(hits) >= 30:
                    return hits
    return hits


def list_draft_rows(drafts_dir):
    rows = []
    folder = Path(drafts_dir)
    if not folder.is_dir():
        return rows
    for path in sorted(folder.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        status = re.search(r"^- \*\*Status:\*\*\s*(.+)$", text, re.MULTILINE)
        task = re.search(r"^- \*\*Task ID:\*\*\s*(\S+)", text, re.MULTILINE)
        rows.append({"name": path.name, "status": status.group(1).strip() if status else None,
                     "task_id": task.group(1) if task else None})
    return rows


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
            elif name == "brief_check":
                result = _text_result(tools.brief_check(args.get("name", "")))
            elif name == "brief_build":
                result = _text_result(tools.brief_build(args))
            elif name == "decision_search":
                result = _text_result(tools.decision_search(args.get("query", "")))
            elif name == "job_detail":
                result = _text_result(tools.job_detail(args.get("job_id", "")))
            elif name == "repo_state":
                result = _text_result(tools.repo_state(args.get("repo", "")))
            elif name == "list_drafts":
                result = _text_result(tools.list_drafts())
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
