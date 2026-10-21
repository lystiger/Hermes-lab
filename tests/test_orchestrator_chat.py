import subprocess

import pytest

from orchestrator import chat as chat_module
from orchestrator.chat import (
    ChatError,
    ClaudeChatProvider,
    ConversationStore,
    OrchestratorChat,
    write_drafts,
)


class FakeProvider:
    def __init__(self, reply="ok", error=None):
        self.reply_text = reply
        self.error = error
        self.calls = []

    def reply(self, system_prompt, messages, model, effort):
        self.calls.append({"system": system_prompt, "messages": list(messages), "model": model, "effort": effort})
        if self.error:
            raise self.error
        return self.reply_text


@pytest.fixture
def lysstack(tmp_path):
    root = tmp_path / "LysStack"
    root.mkdir()
    (root / "AGENTS.md").write_text("# AGENTS\n\nRULE-MARKER: never execute runs.\n", encoding="utf-8")
    return root


@pytest.fixture
def chat(tmp_path, lysstack):
    store = ConversationStore(tmp_path / "state")

    def make(provider):
        return OrchestratorChat(store=store, provider=provider, lysstack_root=lysstack)

    return make


BRIEF = """# Active Task

- **Task ID:** UG-002
- **Status:** Ready

## Goal

Do the thing.
"""


def test_drafts_are_forced_to_draft_status(tmp_path):
    reply = "Here it is.\n```brief-draft path=ug-002.md\n" + BRIEF + "```\n"

    written = write_drafts(reply, tmp_path / "drafts")

    assert written == ["ug-002.md"]
    text = (tmp_path / "drafts" / "ug-002.md").read_text()
    assert "- **Status:** Draft" in text
    assert "- **Status:** Ready" not in text


def test_draft_without_a_status_line_gets_one(tmp_path):
    reply = "```brief-draft path=no-status.md\n# Brief\n\nGoal only.\n```"

    write_drafts(reply, tmp_path / "drafts")

    assert "- **Status:** Draft" in (tmp_path / "drafts" / "no-status.md").read_text()


@pytest.mark.parametrize("name", ["../escape.md", "Upper.md", "a/b.md", ".hidden.md", "notes.txt"])
def test_unsafe_draft_names_are_refused(tmp_path, name):
    reply = f"```brief-draft path={name}\n{BRIEF}```"

    with pytest.raises(ChatError):
        write_drafts(reply, tmp_path / "drafts")
    assert not (tmp_path / "escape.md").exists()


def test_existing_draft_is_never_overwritten(tmp_path):
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    (drafts / "taken.md").write_text("keep me")

    with pytest.raises(ChatError, match="already exists"):
        write_drafts(f"```brief-draft path=taken.md\n{BRIEF}```", drafts)
    assert (drafts / "taken.md").read_text() == "keep me"


def test_turn_saves_the_user_message_then_the_reply_and_its_drafts(chat, lysstack):
    provider = FakeProvider(reply="Drafted.\n```brief-draft path=ug-003.md\n" + BRIEF + "```")
    orchestrator = chat(provider)
    conversation = orchestrator.start("sonnet", "high", "Test")

    message = orchestrator.send(conversation["id"], "Plan the inquiry review.")

    assert message["drafts"] == ["ug-003.md"]
    saved = orchestrator.store.get(conversation["id"])
    assert [m["role"] for m in saved["messages"]] == ["user", "assistant"]
    assert (lysstack / "drafts" / "ug-003.md").exists()


def test_the_system_prompt_carries_the_rules_and_the_snapshot(chat):
    provider = FakeProvider()
    orchestrator = chat(provider)
    conversation = orchestrator.start("opus", None)

    orchestrator.send(conversation["id"], "hello")

    system = provider.calls[0]["system"]
    assert "You draft briefs only" in system
    assert "RULE-MARKER" in system
    assert provider.calls[0]["model"] == "opus"


def test_a_failed_model_call_keeps_the_human_message(chat):
    orchestrator = chat(FakeProvider(error=ChatError("model call failed")))
    conversation = orchestrator.start("sonnet", None)

    with pytest.raises(ChatError):
        orchestrator.send(conversation["id"], "still here?")

    saved = orchestrator.store.get(conversation["id"])
    assert [m["role"] for m in saved["messages"]] == ["user"]


def test_unknown_models_and_efforts_are_refused(chat):
    orchestrator = chat(FakeProvider())
    with pytest.raises(ChatError, match="model"):
        orchestrator.start("gpt-5", None)
    with pytest.raises(ChatError, match="effort"):
        orchestrator.start("sonnet", "ultra")


def test_conversation_ids_cannot_point_outside_the_store(chat, tmp_path):
    orchestrator = chat(FakeProvider())
    with pytest.raises(ChatError, match="unknown conversation"):
        orchestrator.store.get("../../etc/passwd")


def test_claude_provider_runs_with_no_tools_and_no_repository(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["cwd"] = kwargs["cwd"]
        return subprocess.CompletedProcess(argv, 0, stdout="answer\n", stderr="")

    monkeypatch.setattr(chat_module.subprocess, "run", fake_run)

    text = ClaudeChatProvider().reply("SYS", [{"role": "user", "content": "hi"}], "haiku", "low")

    argv = seen["argv"]
    assert text == "answer"
    assert argv[argv.index("--tools") + 1] == ""
    assert "--no-session-persistence" in argv
    assert argv[argv.index("--model") + 1] == "haiku"
    assert argv[argv.index("--effort") + 1] == "low"
    assert "Edit" not in argv and "Bash" not in argv
    assert "Hermes-lab" not in seen["cwd"]


def test_api_has_no_run_or_cancel_routes():
    from fastapi.testclient import TestClient

    import main

    paths = main.app.openapi()["paths"]
    orchestrator_paths = [p for p in paths if p.startswith("/orchestrator")]
    assert orchestrator_paths
    for path in orchestrator_paths:
        assert not any(word in path for word in ("run", "start", "cancel", "merge", "deploy")), path
    assert TestClient(main.app).post("/orchestrator/runs", json={}).status_code == 404
