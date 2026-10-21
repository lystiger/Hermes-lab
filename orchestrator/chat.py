"""Orchestrator chat: a draft-only conversation with a model.

The orchestrator talks to a model through a chat-only adapter. The adapter sends a
prompt and returns text. It has no working directory and no tools, so a model cannot
edit files or run commands. The only write path is the brief-draft writer, which
writes into LysStack/drafts/ and always marks the draft as Draft. Nothing here starts,
cancels, or merges a run.
"""

import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

CLAUDE_MODELS = ("claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5")
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
DRAFT_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}\.md$")
DRAFT_BLOCK = re.compile(r"```brief-draft\s+path=(\S+)\n(.*?)\n```", re.DOTALL)
STATUS_LINE = re.compile(r"^- \*\*Status:\*\*.*$", re.MULTILINE)
DEFAULT_TITLE = "New orchestrator chat"
CHAT_TIMEOUT_SECONDS = 300
TITLE_MAX = 120
TOOL_NAMES = ("lysstack_list", "lysstack_read", "hermes_jobs", "hermes_capacity", "draft_save")

DRAFT_RULES = """You are the orchestrator in LysStack. You help Lystiger shape a task brief.

Rules you must follow:
- Address the user as Lystiger. Never call them "the human" or "a human".
- You draft briefs only. You never set a brief to Ready and you never start a run.
- Ask grill-me questions when a task is big, in batches of at most five.
- Tools: lysstack_list, lysstack_read (read LysStack), hermes_jobs and hermes_capacity (read Hermes status), and draft_save (save a brief as Draft). Use draft_save for briefs. Nothing else is available.
- If draft_save is not available, reply with a fenced block instead:
  ```brief-draft path=<name>.md
  <full brief in LysStack active_task format>
  ```
  The name is lowercase letters, digits and hyphens. The server forces the status to Draft.
- Anything you are not sure of is UNPROVEN, not a guess.

LysStack rules, verbatim from AGENTS.md:
"""

COMPACT_RULES = (
    "Summarize this conversation so it can continue later with less context. Keep the goal, "
    "decisions made, brief drafts and their names, open questions, and what Lystiger asked for last. "
    "Under 400 words. Reply with the summary only."
)


class ChatError(RuntimeError):
    """A chat request cannot be served."""


@dataclass
class ChatReply:
    text: str
    usage: dict = field(default_factory=dict)


def _usage_from(payload):
    """The context a call used, from the CLI's usage and modelUsage fields."""
    usage = payload.get("usage") or {}
    model_usage = next(iter((payload.get("modelUsage") or {}).values()), {})
    cache_read = usage.get("cache_read_input_tokens", 0)
    cache_creation = usage.get("cache_creation_input_tokens", 0)
    return {
        "context_tokens": usage.get("input_tokens", 0) + cache_read + cache_creation,
        "cache_read_tokens": cache_read,
        "cache_creation_tokens": cache_creation,
        "output_tokens": usage.get("output_tokens", 0),
        "context_window": model_usage.get("contextWindow"),
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


class ClaudeChatProvider:
    """Sends one prompt to the Claude CLI with no tools and no working repository."""

    def __init__(self, binary="claude", timeout=CHAT_TIMEOUT_SECONDS, tools=None):
        """tools: None for no tools, or {"python", "repo", "root", "drafts"} to serve the LysStack tools."""
        self.binary = binary
        self.timeout = timeout
        self.tools = tools

    def reply(self, system_prompt, messages, model, effort):
        if model not in CLAUDE_MODELS:
            raise ChatError(f"model must be one of {', '.join(CLAUDE_MODELS)}")
        if effort is not None and effort not in EFFORT_LEVELS:
            raise ChatError(f"effort must be one of {', '.join(EFFORT_LEVELS)}")
        argv = [
            self.binary, "-p",
            # Orchestrator calls always skip permission prompts, as the operator chose.
            "--dangerously-skip-permissions",
            "--tools", "",
            "--no-session-persistence",
            "--output-format", "json",
            "--model", model,
            "--system-prompt", system_prompt,
        ]
        if effort:
            argv += ["--effort", effort]
        with tempfile.TemporaryDirectory(prefix="orchestrator-") as neutral:
            if self.tools:
                argv += self._tool_args(neutral)
            return self._run(argv, messages, neutral)

    def _tool_args(self, neutral):
        """Only the LysStack tools: a strict MCP config, and an allow list with exactly those tools."""
        config = {"mcpServers": {"lysstack": {
            "command": self.tools["python"],
            "args": ["-m", "orchestrator.tools_server", "--root", str(self.tools["root"]),
                     "--drafts", str(self.tools["drafts"])],
            "env": {"PYTHONPATH": str(self.tools["repo"])},
        }}}
        config_path = Path(neutral) / "mcp.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        allowed = [f"mcp__lysstack__{name}" for name in TOOL_NAMES]
        return ["--strict-mcp-config", "--mcp-config", str(config_path), "--allowedTools", *allowed]

    def _run(self, argv, messages, neutral):
        transcript = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
        try:
            result = subprocess.run(
                argv, input=transcript, capture_output=True, text=True,
                cwd=neutral, timeout=self.timeout, check=False, stdin=None,
            )
        except subprocess.TimeoutExpired as exc:
            raise ChatError("model did not answer in time") from exc
        if result.returncode != 0:
            raise ChatError(f"model call failed: {result.stderr.strip()[:300]}")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ChatError("model returned an unreadable answer") from exc
        if payload.get("is_error"):
            raise ChatError(f"model call failed: {str(payload.get('result', ''))[:300]}")
        return ChatReply(text=str(payload.get("result", "")).strip(), usage=_usage_from(payload))


def write_drafts(reply, drafts_dir):
    """Save every brief-draft block in the reply. Returns the file names written."""
    written = []
    for name, body in DRAFT_BLOCK.findall(reply):
        if not DRAFT_NAME.match(name):
            raise ChatError(f"draft name '{name}' must be lowercase letters, digits and hyphens, ending in .md")
        target = Path(drafts_dir) / name
        if target.exists():
            raise ChatError(f"draft '{name}' already exists; pick a new name")
        if STATUS_LINE.search(body):
            body = STATUS_LINE.sub("- **Status:** Draft", body, count=1)
        else:
            body = body + "\n- **Status:** Draft\n"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body + ("" if body.endswith("\n") else "\n"), encoding="utf-8")
        written.append(name)
    return written


class ConversationStore:
    """One JSON file per conversation, kept outside the repository."""

    def __init__(self, root):
        self.root = Path(root)

    def _path(self, conversation_id):
        if not re.fullmatch(r"[a-f0-9]{12}", conversation_id):
            raise ChatError("unknown conversation")
        return self.root / f"{conversation_id}.json"

    def create(self, model, effort, title, system_commit):
        self.root.mkdir(parents=True, exist_ok=True)
        conversation = {
            "id": uuid.uuid4().hex[:12],
            "title": title or DEFAULT_TITLE,
            "model": model,
            "effort": effort,
            "system_commit": system_commit,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "messages": [],
            "usage": None,
            "summary": None,
            "summary_upto": 0,
        }
        self.save(conversation)
        return conversation

    def save(self, conversation):
        path = self._path(conversation["id"])
        path.write_text(json.dumps(conversation, indent=2, ensure_ascii=False), encoding="utf-8")

    def get(self, conversation_id):
        path = self._path(conversation_id)
        if not path.exists():
            raise ChatError("unknown conversation")
        return json.loads(path.read_text(encoding="utf-8"))

    def delete(self, conversation_id):
        path = self._path(conversation_id)
        if not path.exists():
            raise ChatError("unknown conversation")
        path.unlink()

    def list(self):
        if not self.root.exists():
            return []
        items = [json.loads(p.read_text(encoding="utf-8")) for p in self.root.glob("*.json")]
        return sorted(({k: v for k, v in c.items() if k != "messages"} for c in items),
                      key=lambda c: c["created"], reverse=True)


class OrchestratorChat:
    """Runs a turn: append the human message, ask the model, save the reply, write drafts."""

    def __init__(self, store, provider, lysstack_root, drafts_dir=None):
        self.store = store
        self.provider = provider
        self.lysstack_root = Path(lysstack_root)
        self.drafts_dir = Path(drafts_dir) if drafts_dir else self.lysstack_root / "drafts"

    def system_prompt(self):
        rules = (self.lysstack_root / "AGENTS.md").read_text(encoding="utf-8")
        return DRAFT_RULES + rules

    def system_commit(self):
        try:
            out = subprocess.run(["git", "-C", str(self.lysstack_root), "rev-parse", "HEAD"],
                                 capture_output=True, text=True, check=False)
            return out.stdout.strip() if out.returncode == 0 else "unknown"
        except OSError:
            return "unknown"

    def prompt_messages(self, conversation):
        """What the model sees: the summary of older messages, then the newer messages."""
        newer = conversation["messages"][conversation.get("summary_upto", 0):]
        if not conversation.get("summary"):
            return newer
        summary = {"role": "user", "content": "Summary of the earlier conversation:\n" + conversation["summary"]}
        return [summary] + newer

    def start(self, model, effort, title=None):
        if model not in CLAUDE_MODELS:
            raise ChatError(f"model must be one of {', '.join(CLAUDE_MODELS)}")
        if effort is not None and effort not in EFFORT_LEVELS:
            raise ChatError(f"effort must be one of {', '.join(EFFORT_LEVELS)}")
        return self.store.create(model, effort, title, self.system_commit())

    def update(self, conversation_id, title=None, model=None, effort=None, effort_given=False):
        """Rename a chat, or change its model or effort. Only the fields given are changed."""
        conversation = self.store.get(conversation_id)
        if title is not None:
            title = title.strip()
            if not title or len(title) > TITLE_MAX:
                raise ChatError(f"title must be 1 to {TITLE_MAX} characters")
            conversation["title"] = title
        if model is not None:
            if model not in CLAUDE_MODELS:
                raise ChatError(f"model must be one of {', '.join(CLAUDE_MODELS)}")
            conversation["model"] = model
        if effort_given:
            if effort is not None and effort not in EFFORT_LEVELS:
                raise ChatError(f"effort must be one of {', '.join(EFFORT_LEVELS)}")
            conversation["effort"] = effort
        self.store.save(conversation)
        return {k: v for k, v in conversation.items() if k != "messages"}

    def delete(self, conversation_id):
        self.store.delete(conversation_id)

    def send(self, conversation_id, content):
        content = (content or "").strip()
        if not content:
            raise ChatError("message is empty")
        conversation = self.store.get(conversation_id)
        conversation["messages"].append({"role": "user", "content": content, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
        self.store.save(conversation)
        result = self.provider.reply(self.system_prompt(), self.prompt_messages(conversation),
                                     conversation["model"], conversation["effort"])
        drafts = write_drafts(result.text, self.drafts_dir)
        conversation["usage"] = result.usage or None
        conversation["messages"].append({"role": "assistant", "content": result.text, "drafts": drafts,
                                         "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
        self.store.save(conversation)
        return conversation["messages"][-1]

    def compact(self, conversation_id):
        """Summarize everything so far, so later turns send the summary instead of the full history."""
        conversation = self.store.get(conversation_id)
        if len(conversation["messages"]) <= conversation.get("summary_upto", 0):
            raise ChatError("nothing new to compact")
        transcript = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in self.prompt_messages(conversation))
        result = self.provider.reply(COMPACT_RULES, [{"role": "user", "content": transcript}],
                                     conversation["model"], None)
        conversation["summary"] = result.text
        conversation["summary_upto"] = len(conversation["messages"])
        conversation["usage"] = None
        self.store.save(conversation)
        return {k: v for k, v in conversation.items() if k != "messages"}


def default_state_dir():
    return Path(os.environ.get("HERMES_ORCHESTRATOR_DIR",
                               Path.home() / ".local" / "state" / "hermes" / "orchestrator"))
