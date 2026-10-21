import json
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
    def __init__(self, reply="ok", error=None, title="A short title", usage=None):
        self.reply_text = reply
        self.title_text = title
        self.error = error
        self.usage = usage or {"context_tokens": 1200, "cache_read_tokens": 1000, "cache_creation_tokens": 200,
                               "output_tokens": 5, "context_window": 1000000}
        self.calls = []

    def reply(self, system_prompt, messages, model, effort):
        self.calls.append({"system": system_prompt, "messages": list(messages), "model": model, "effort": effort})
        if self.error:
            raise self.error
        # The title call uses its own system prompt; everything else is a chat or compact reply.
        text = self.title_text if system_prompt == chat_module.TITLE_RULES else self.reply_text
        return chat_module.ChatReply(text=text, usage=self.usage)


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
    conversation = orchestrator.start("claude-sonnet-5-5", "high", "Test")

    message = orchestrator.send(conversation["id"], "Plan the inquiry review.")

    assert message["drafts"] == ["ug-003.md"]
    saved = orchestrator.store.get(conversation["id"])
    assert [m["role"] for m in saved["messages"]] == ["user", "assistant"]
    assert (lysstack / "drafts" / "ug-003.md").exists()


def test_the_system_prompt_carries_the_rules_and_the_snapshot(chat):
    provider = FakeProvider()
    orchestrator = chat(provider)
    conversation = orchestrator.start("claude-opus-5-5", None)

    orchestrator.send(conversation["id"], "hello")

    system = provider.calls[0]["system"]
    assert "You draft briefs only" in system
    assert "RULE-MARKER" in system
    assert provider.calls[0]["model"] == "claude-opus-5-5"


def test_a_failed_model_call_keeps_the_human_message(chat):
    orchestrator = chat(FakeProvider(error=ChatError("model call failed")))
    conversation = orchestrator.start("claude-sonnet-5-5", None)

    with pytest.raises(ChatError):
        orchestrator.send(conversation["id"], "still here?")

    saved = orchestrator.store.get(conversation["id"])
    assert [m["role"] for m in saved["messages"]] == ["user"]


def test_unknown_models_and_efforts_are_refused(chat):
    orchestrator = chat(FakeProvider())
    with pytest.raises(ChatError, match="model"):
        orchestrator.start("gpt-5", None)
    with pytest.raises(ChatError, match="effort"):
        orchestrator.start("claude-sonnet-5-5", "ultra")


def test_conversation_ids_cannot_point_outside_the_store(chat, tmp_path):
    orchestrator = chat(FakeProvider())
    with pytest.raises(ChatError, match="unknown conversation"):
        orchestrator.store.get("../../etc/passwd")


def test_claude_provider_runs_with_no_tools_and_no_repository(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["cwd"] = kwargs["cwd"]
        payload = {"result": "answer", "is_error": False,
                   "usage": {"input_tokens": 2, "cache_read_input_tokens": 3024, "cache_creation_input_tokens": 505,
                             "output_tokens": 4},
                   "modelUsage": {"claude-opus-5-5": {"contextWindow": 1000000}}}
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(chat_module.subprocess, "run", fake_run)

    reply = ClaudeChatProvider().reply("SYS", [{"role": "user", "content": "hi"}], "claude-opus-5-5", "low")
    text = reply.text
    assert reply.usage["context_tokens"] == 2 + 3024 + 505
    assert reply.usage["context_window"] == 1000000
    assert "--output-format" in seen["argv"]

    argv = seen["argv"]
    assert text == "answer"
    assert argv[argv.index("--tools") + 1] == ""
    assert "--no-session-persistence" in argv
    assert "--dangerously-skip-permissions" in argv
    assert argv[argv.index("--model") + 1] == "claude-opus-5-5"
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


def test_rename_trims_and_keeps_the_chat(chat):
    orchestrator = chat(FakeProvider())
    conversation = orchestrator.start("claude-sonnet-5-5", None, "Old")

    updated = orchestrator.update(conversation["id"], title="  Inquiry review plan  ")

    assert updated["title"] == "Inquiry review plan"
    assert orchestrator.store.get(conversation["id"])["title"] == "Inquiry review plan"


@pytest.mark.parametrize("title", ["", "   ", "x" * 121])
def test_a_blank_or_long_title_is_refused(chat, title):
    orchestrator = chat(FakeProvider())
    conversation = orchestrator.start("claude-sonnet-5-5", None)

    with pytest.raises(ChatError, match="title"):
        orchestrator.update(conversation["id"], title=title)


def test_model_and_effort_change_only_when_given(chat):
    orchestrator = chat(FakeProvider())
    conversation = orchestrator.start("claude-sonnet-5-5", "high", "Chat")

    orchestrator.update(conversation["id"], model="claude-opus-5-5")
    saved = orchestrator.store.get(conversation["id"])
    assert (saved["model"], saved["effort"]) == ("claude-opus-5-5", "high")

    orchestrator.update(conversation["id"], effort=None, effort_given=True)
    assert orchestrator.store.get(conversation["id"])["effort"] is None

    with pytest.raises(ChatError):
        orchestrator.update(conversation["id"], model="gpt-5")


def test_delete_removes_the_chat(chat):
    orchestrator = chat(FakeProvider())
    conversation = orchestrator.start("claude-sonnet-5-5", None)

    orchestrator.delete(conversation["id"])

    assert conversation["id"] not in [c["id"] for c in orchestrator.store.list()]
    with pytest.raises(ChatError, match="unknown conversation"):
        orchestrator.store.get(conversation["id"])
    with pytest.raises(ChatError, match="unknown conversation"):
        orchestrator.delete(conversation["id"])


def test_api_renames_and_deletes_a_chat(chat, monkeypatch):
    from fastapi.testclient import TestClient

    import main
    from orchestrator import api

    orchestrator = chat(FakeProvider())
    monkeypatch.setattr(api, "get_chat", lambda: orchestrator)
    client = TestClient(main.app)
    conversation = client.post("/orchestrator/conversations", json={"model": "claude-sonnet-5-5"}).json()
    url = f"/orchestrator/conversations/{conversation['id']}"

    assert client.patch(url, json={"title": "Renamed"}).json()["title"] == "Renamed"
    assert client.patch(url, json={"title": "   "}).status_code == 400
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404
    assert client.delete(url).status_code == 404
    assert client.patch("/orchestrator/conversations/aaaaaaaaaaaa", json={"title": "x"}).status_code == 404


def test_a_new_chat_is_named_from_its_first_reply(chat):
    orchestrator = chat(FakeProvider(title='"Inquiry review plan"\nextra line'))
    conversation = orchestrator.start("claude-sonnet-5-5", None)

    orchestrator.send(conversation["id"], "Plan the inquiry review workspace")

    assert orchestrator.store.get(conversation["id"])["title"] == "Inquiry review plan"


def test_a_failed_title_call_falls_back_to_the_first_words(chat):
    class TitleFails(FakeProvider):
        def reply(self, system_prompt, messages, model, effort):
            if system_prompt == chat_module.TITLE_RULES:
                raise ChatError("title call failed")
            return super().reply(system_prompt, messages, model, effort)

    orchestrator = chat(TitleFails())
    conversation = orchestrator.start("claude-sonnet-5-5", None)

    orchestrator.send(conversation["id"], "one two three four five six seven eight")

    assert orchestrator.store.get(conversation["id"])["title"] == "one two three four five six"


def test_a_renamed_chat_keeps_its_name(chat):
    orchestrator = chat(FakeProvider())
    conversation = orchestrator.start("claude-sonnet-5-5", None, "My name")

    orchestrator.send(conversation["id"], "hello")

    assert orchestrator.store.get(conversation["id"])["title"] == "My name"


def test_the_last_call_usage_is_saved_on_the_chat(chat):
    orchestrator = chat(FakeProvider())
    conversation = orchestrator.start("claude-sonnet-5-5", None)

    orchestrator.send(conversation["id"], "hello")

    assert orchestrator.store.get(conversation["id"])["usage"]["context_tokens"] == 1200


def test_compact_summarizes_and_later_turns_send_the_summary_and_newer_messages(chat):
    provider = FakeProvider(reply="reply text")
    orchestrator = chat(provider)
    conversation = orchestrator.start("claude-sonnet-5-5", None, "Chat")
    orchestrator.send(conversation["id"], "first question")
    provider.reply_text = "Goal: plan the review. Decided: use a table."

    result = orchestrator.compact(conversation["id"])

    assert result["summary"] == "Goal: plan the review. Decided: use a table."
    assert result["summary_upto"] == 2
    provider.reply_text = "next"
    orchestrator.send(conversation["id"], "second question")
    sent = provider.calls[-1]["messages"]
    assert sent[0]["content"].startswith("Summary of the earlier conversation:")
    assert [m["content"] for m in sent[1:]] == ["second question"]


def test_compact_needs_something_new(chat):
    orchestrator = chat(FakeProvider())
    conversation = orchestrator.start("claude-sonnet-5-5", None)
    orchestrator.send(conversation["id"], "hello")
    orchestrator.compact(conversation["id"])

    with pytest.raises(ChatError, match="nothing new"):
        orchestrator.compact(conversation["id"])


def test_api_compacts_a_chat_and_reports_unknown_ids(chat, monkeypatch):
    from fastapi.testclient import TestClient

    import main
    from orchestrator import api

    orchestrator = chat(FakeProvider(reply="reply"))
    monkeypatch.setattr(api, "get_chat", lambda: orchestrator)
    client = TestClient(main.app)
    conversation = client.post("/orchestrator/conversations", json={"model": "claude-sonnet-5-5"}).json()
    client.post(f"/orchestrator/conversations/{conversation['id']}/messages", json={"content": "hi"})

    assert client.post(f"/orchestrator/conversations/{conversation['id']}/compact").status_code == 200
    assert client.post("/orchestrator/conversations/aaaaaaaaaaaa/compact").status_code == 404


@pytest.mark.parametrize("raw, expected", [
    ('Title: Inquiry Review Workspace', "Inquiry Review Workspace"),
    ('**Chat title:** "Staff inquiry plan"', "Staff inquiry plan"),
    ("  Plain title  \nsecond line", "Plain title"),
    ("", "fallback"),
])
def test_model_titles_are_cleaned_for_the_list(raw, expected):
    assert chat_module.clean_title(raw, "fallback") == expected
