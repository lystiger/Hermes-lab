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
from pathlib import Path

CLAUDE_MODELS = ("claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5")
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
DRAFT_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}\.md$")
DRAFT_BLOCK = re.compile(r"```brief-draft\s+path=(\S+)\n(.*?)\n```", re.DOTALL)
STATUS_LINE = re.compile(r"^- \*\*Status:\*\*.*$", re.MULTILINE)
CHAT_TIMEOUT_SECONDS = 300

DRAFT_RULES = """You are the orchestrator in LysStack. You help a human shape a task brief.

Rules you must follow:
- You draft briefs only. You never set a brief to Ready and you never start a run.
- Ask grill-me questions when a task is big, in batches of at most five.
- To save a draft, reply with a fenced block:
  ```brief-draft path=<name>.md
  <full brief in LysStack active_task format>
  ```
  The name is lowercase letters, digits and hyphens. The server forces the status to Draft.
- Anything you are not sure of is UNPROVEN, not a guess.

LysStack rules, verbatim from AGENTS.md:
"""


class ChatError(RuntimeError):
    """A chat request cannot be served."""


class ClaudeChatProvider:
    """Sends one prompt to the Claude CLI with no tools and no working repository."""

    def __init__(self, binary="claude", timeout=CHAT_TIMEOUT_SECONDS):
        self.binary = binary
        self.timeout = timeout

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
            "--model", model,
            "--system-prompt", system_prompt,
        ]
        if effort:
            argv += ["--effort", effort]
        transcript = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
        with tempfile.TemporaryDirectory(prefix="orchestrator-") as neutral:
            try:
                result = subprocess.run(
                    argv, input=transcript, capture_output=True, text=True,
                    cwd=neutral, timeout=self.timeout, check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise ChatError("model did not answer in time") from exc
        if result.returncode != 0:
            raise ChatError(f"model call failed: {result.stderr.strip()[:300]}")
        return result.stdout.strip()


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
            "title": title or "New orchestrator chat",
            "model": model,
            "effort": effort,
            "system_commit": system_commit,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "messages": [],
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

    def start(self, model, effort, title=None):
        if model not in CLAUDE_MODELS:
            raise ChatError(f"model must be one of {', '.join(CLAUDE_MODELS)}")
        if effort is not None and effort not in EFFORT_LEVELS:
            raise ChatError(f"effort must be one of {', '.join(EFFORT_LEVELS)}")
        return self.store.create(model, effort, title, self.system_commit())

    def send(self, conversation_id, content):
        content = (content or "").strip()
        if not content:
            raise ChatError("message is empty")
        conversation = self.store.get(conversation_id)
        conversation["messages"].append({"role": "user", "content": content, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
        self.store.save(conversation)
        reply = self.provider.reply(self.system_prompt(), conversation["messages"],
                                    conversation["model"], conversation["effort"])
        drafts = write_drafts(reply, self.drafts_dir)
        conversation["messages"].append({"role": "assistant", "content": reply, "drafts": drafts,
                                         "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
        self.store.save(conversation)
        return conversation["messages"][-1]


def default_state_dir():
    return Path(os.environ.get("HERMES_ORCHESTRATOR_DIR",
                               Path.home() / ".local" / "state" / "hermes" / "orchestrator"))
