"""End to end: the real Claude CLI, the LysStack tools, and a draft. Spends quota, so it runs only with RUN_E2E=1."""

import os
import pwd
from pathlib import Path

import pytest

from orchestrator.api import tools_config
from orchestrator.chat import ClaudeChatProvider, ConversationStore, OrchestratorChat

REPO = Path(__file__).resolve().parent.parent
LYSSTACK = Path(os.environ.get("HERMES_LYSSTACK_ROOT", Path.home() / "Projects" / "LysStack"))

pytestmark = pytest.mark.skipif(os.environ.get("RUN_E2E") != "1", reason="set RUN_E2E=1 to run the real model")


def test_the_model_saves_a_draft_through_the_tool_and_nothing_runs(tmp_path, monkeypatch):
    # The suite gives each test a temporary HOME. The Claude CLI needs the real one for its login.
    monkeypatch.setenv("HOME", pwd.getpwuid(os.getuid()).pw_dir)
    drafts = tmp_path / "drafts"
    tools = tools_config(LYSSTACK)
    tools["drafts"] = drafts
    chat = OrchestratorChat(
        store=ConversationStore(tmp_path / "state"),
        provider=ClaudeChatProvider(tools=tools),
        lysstack_root=LYSSTACK,
        drafts_dir=drafts,
    )
    conversation = chat.start("claude-haiku-5-5", None, "E2E")

    chat.send(conversation["id"],
              "Use the draft_save tool to save a brief named e2e-smoke.md. Its body is a one-line goal: "
              "'Smoke test of the draft tool.' Then tell me the tool's result in one sentence.")

    saved = drafts / "e2e-smoke.md"
    assert saved.exists(), "the model did not save the draft through the tool"
    assert "- **Status:** Draft" in saved.read_text()
    assert not (LYSSTACK / "drafts" / "e2e-smoke.md").exists()
