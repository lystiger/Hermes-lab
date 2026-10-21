import json
import subprocess

import pytest

from orchestrator import chat as chat_module
from orchestrator import tools_server
from orchestrator.chat import ClaudeChatProvider
from orchestrator.tools_server import ToolError, LysStackTools, analyze_usage, build_brief, check_brief, handle, repo_state_for, search_knowledge


@pytest.fixture
def root(tmp_path):
    lysstack = tmp_path / "LysStack"
    (lysstack / "operating_system").mkdir(parents=True)
    (lysstack / "operating_system" / "current_focus.md").write_text("focus\n")
    (lysstack / "AGENTS.md").write_text("# rules\n")
    (lysstack / "operating_system" / "active_task.md").write_text("# Active Task\n")
    (lysstack / ".git").mkdir()
    (lysstack / ".git" / "config").write_text("secret\n")
    return lysstack


def _call(tools, name, arguments):
    response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": arguments}}, tools)
    return response["result"]


def test_the_server_offers_exactly_the_agreed_tools(root):
    response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, LysStackTools(root))

    names = [t["name"] for t in response["result"]["tools"]]
    assert set(names) == set(tools_server.TOOL_NAMES)
    assert len(names) == len(set(names)) == 13
    assert "draft_save" in names and "start_run" not in names


def test_notifications_get_no_answer(root):
    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, LysStackTools(root)) is None


def test_list_and_read_stay_inside_lysstack(root):
    tools = LysStackTools(root)

    assert _call(tools, "lysstack_list", {"scope": "operating_system"})["content"][0]["text"] == \
        json.dumps(["operating_system/active_task.md", "operating_system/current_focus.md"], indent=2)
    assert _call(tools, "lysstack_read", {"path": "AGENTS.md"})["content"][0]["text"] == "# rules\n"
    assert _call(tools, "lysstack_read", {"path": "../outside.md"})["isError"] is True
    assert _call(tools, "lysstack_read", {"path": ".git/config"})["isError"] is True
    assert _call(tools, "lysstack_list", {"scope": "everything"})["isError"] is True


def test_long_files_are_cut_at_the_limit(root):
    (root / "big.md").write_text("x" * (tools_server.MAX_READ_BYTES + 10))

    text = _call(LysStackTools(root), "lysstack_read", {"path": "big.md"})["content"][0]["text"]

    assert text.endswith("[truncated at 64 KB]")


def test_draft_save_writes_a_draft_only(root, tmp_path):
    drafts = tmp_path / "drafts"
    tools = LysStackTools(root, drafts_dir=drafts)

    result = _call(tools, "draft_save", {"name": "new-brief.md", "body": "# Brief\n\n- **Status:** Ready\n"})

    assert result["isError"] is False
    text = (drafts / "new-brief.md").read_text()
    assert "- **Status:** Draft" in text and "Ready" not in text


@pytest.mark.parametrize("name", ["../escape.md", "Upper.md", "notes.txt"])
def test_draft_save_refuses_unsafe_names(root, tmp_path, name):
    result = _call(LysStackTools(root, drafts_dir=tmp_path / "drafts"), "draft_save", {"name": name, "body": "x"})

    assert result["isError"] is True


def test_hermes_tools_report_when_the_api_is_down(root):
    tools = LysStackTools(root, api="http://127.0.0.1:9")

    assert _call(tools, "hermes_jobs", {})["isError"] is True
    assert _call(tools, "hermes_capacity", {})["isError"] is True


def test_unknown_tools_are_refused(root):
    assert _call(LysStackTools(root), "start_run", {})["isError"] is True


def test_the_model_gets_only_the_lysstack_tools(monkeypatch, root, tmp_path):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        config_path = argv[argv.index("--mcp-config") + 1]
        seen["config"] = json.loads(open(config_path).read())
        payload = {"result": "ok", "is_error": False, "usage": {}, "modelUsage": {}}
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(chat_module.subprocess, "run", fake_run)
    provider = ClaudeChatProvider(tools={"python": "/usr/bin/python3", "repo": root, "root": root,
                                         "drafts": tmp_path / "drafts", "state": tmp_path / "state"})

    provider.reply("SYS", [{"role": "user", "content": "hi"}], "claude-haiku-5-5", None)

    argv = seen["argv"]
    assert "--strict-mcp-config" in argv
    allowed = argv[argv.index("--allowedTools") + 1:]
    assert allowed == [f"mcp__lysstack__{n}" for n in tools_server.TOOL_NAMES]
    assert not any(tool in argv for tool in ("Bash", "Edit", "Write"))
    server = seen["config"]["mcpServers"]["lysstack"]
    assert server["args"][-4:] == ["--drafts", str(tmp_path / "drafts"), "--state", str(tmp_path / "state")]
    assert server["env"]["PYTHONPATH"] == str(root)


QUOTA = {
    "claude": {"id": "claude", "ready": True, "status": "ok", "leftPct": 92, "resetsAt": "2026-10-26"},
    "codex": {"id": "codex", "ready": True, "status": "ok", "leftPct": 4, "resetsAt": "2026-10-27"},
    "agy": {"id": "agy", "ready": False, "status": "unknown", "leftPct": None, "resetsAt": None},
}


def test_analysis_flags_low_quota_unready_agents_and_full_chats():
    chats = [{"id": "a", "title": "Long one", "summary": None,
              "usage": {"context_tokens": 900, "context_window": 1000}},
             {"id": "b", "title": "Mid one", "summary": "s",
              "usage": {"context_tokens": 650, "context_window": 1000}},
             {"id": "c", "title": "Fresh", "usage": None}]

    result = analyze_usage(QUOTA, chats)

    text = " ".join(result["recommendations"])
    assert "Avoid agy" in text
    assert "codex has 4% left" in text and "2026-10-27" in text
    assert "'Long one' is 90% full: compact it now." in text
    assert "'Mid one' is 65% full: compact it soon." in text
    assert "claude" not in text
    assert [c["id"] for c in result["chats"]] == ["a", "b"]


def test_a_healthy_session_says_no_action_is_needed():
    healthy = {"claude": {"id": "claude", "ready": True, "status": "ok", "leftPct": 90}}

    assert analyze_usage(healthy, [])["recommendations"] == ["No action needed."]


def test_usage_analysis_reads_the_saved_chats(root, tmp_path, monkeypatch):
    from orchestrator.chat import ConversationStore

    state = tmp_path / "state"
    store = ConversationStore(state)
    chat = store.create("claude-sonnet-5-5", None, "Busy", "commit")
    chat["usage"] = {"context_tokens": 950, "context_window": 1000}
    store.save(chat)
    tools = LysStackTools(root, state_dir=state, api="http://127.0.0.1:9")

    result = tools.usage_analysis()

    assert result["chats"][0]["title"] == "Busy"
    assert any("compact it now" in r for r in result["recommendations"])


def test_agent_options_merges_models_with_quota(root, monkeypatch):
    tools = LysStackTools(root)
    models = {
        "claude": {"allowed": ["claude-sonnet-5-5", "claude-opus-5-5"], "configured": {"default": "claude-sonnet-5-5"}},
        "codex": {"allowed": ["gpt-6.1-sol"], "configured": None},
    }
    monkeypatch.setattr(tools, "_get", lambda path: {"agents": list(QUOTA.values())} if path == "/capacity/limits" else models)

    rows = {r["id"]: r for r in tools.agent_options()}

    assert rows["claude"]["allowed"] == ["claude-sonnet-5-5", "claude-opus-5-5"]
    assert rows["claude"]["leftPct"] == 92
    assert rows["antigravity"]["ready"] is False


def test_both_analysis_tools_still_answer_when_hermes_is_down(root):
    tools = LysStackTools(root, api="http://127.0.0.1:9")

    assert _call(tools, "agent_options", {})["isError"] is False
    assert _call(tools, "usage_analysis", {})["isError"] is False


def test_gemini_agy_and_antigravity_are_one_agent(root, monkeypatch):
    tools = LysStackTools(root)
    models = {"gemini": {"allowed": ["gemini-3.8-flash-high"], "configured": {"default": "gemini-3.8-flash-high"}}}
    capacity = {"agents": [{"id": "agy", "ready": True, "status": "ok", "leftPct": 75, "resetsAt": "2026-10-26"}]}
    monkeypatch.setattr(tools, "_get", lambda path: capacity if path == "/capacity/limits" else models)

    rows = tools.agent_options()

    assert [r["id"] for r in rows] == ["antigravity"]
    assert rows[0]["leftPct"] == 75
    assert rows[0]["allowed"] == ["gemini-3.8-flash-high"]


SHA_A = "a" * 40
GOOD_FIELDS = {
    "task_id": "UG-009", "goal": "Do the thing.", "repository": "lystiger/Unigreen", "baseline": SHA_A,
    "context_files": ["operating_system/active_task.md"],
    "acceptance": ["It works", "It is tested"], "verification": ["pytest -q"], "non_goals": ["No redesign"],
}


def test_a_built_brief_passes_its_own_check(root):
    text = build_brief(GOOD_FIELDS)

    checks = check_brief(text, root)

    assert all(c["ok"] for c in checks), [c for c in checks if not c["ok"]]
    assert "- **Status:** Draft" in text


def test_build_refuses_a_short_baseline_and_empty_criteria(root):
    with pytest.raises(ToolError):
        build_brief({**GOOD_FIELDS, "baseline": "069aed0"})
    with pytest.raises(ToolError):
        build_brief({**GOOD_FIELDS, "acceptance": []})


def test_check_flags_a_ready_status_and_missing_files(root):
    text = build_brief(GOOD_FIELDS).replace("- **Status:** Draft", "- **Status:** Ready")
    text = text.replace("`operating_system/active_task.md`", "`operating_system/missing.md`")

    failed = {c["check"] for c in check_brief(text, root) if not c["ok"]}

    assert "status is Draft" in failed
    assert "context file exists: operating_system/missing.md" in failed


def test_check_reads_a_saved_draft_by_name(root, tmp_path):
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    (drafts / "ug-009.md").write_text(build_brief(GOOD_FIELDS))
    tools = LysStackTools(root, drafts_dir=drafts)

    assert all(c["ok"] for c in tools.brief_check("ug-009.md"))
    assert _call(tools, "brief_check", {"name": "../secret.md"})["isError"] is True


def test_decision_search_finds_lines_and_refuses_one_letter(root):
    (root / "projects" / "unigreen").mkdir(parents=True)
    (root / "projects" / "unigreen" / "decisions.md").write_text("### Decision 001\n- **Decision:** use FastAPI\n")

    hits = search_knowledge(root, "fastapi")

    assert hits == [{"file": "projects/unigreen/decisions.md", "line": 2, "text": "- **Decision:** use FastAPI"}]
    with pytest.raises(ToolError):
        search_knowledge(root, "x")


def test_list_drafts_shows_status_and_task(root, tmp_path):
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    (drafts / "one.md").write_text(build_brief(GOOD_FIELDS))

    rows = tools_server.list_draft_rows(drafts)

    assert rows == [{"name": "one.md", "status": "Draft", "task_id": "UG-009"}]


def test_repo_state_checks_the_pinned_baseline_and_cleanliness(tmp_path):
    import subprocess as sp

    repo = tmp_path / "Unigreen"
    repo.mkdir()
    sp.run(["git", "-C", str(repo), "init", "-q"], check=True)
    sp.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
            "--allow-empty", "-m", "base"], check=True)
    base = sp.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    state = repo_state_for("Unigreen", projects=tmp_path, baseline_from=base)

    assert state["baseline_present"] is True and state["on_baseline"] is True and state["clean"] is True
    assert state["commits_after_baseline"] == 0
    with pytest.raises(ToolError):
        repo_state_for("../etc", projects=tmp_path)
    with pytest.raises(ToolError):
        repo_state_for("NotThere", projects=tmp_path)


def test_job_detail_returns_the_useful_fields(root, monkeypatch):
    tools = LysStackTools(root)
    monkeypatch.setattr(tools, "_get", lambda path: {"id": "run_1", "status": "FAILED", "blockedReason": "verifier",
                                                    "currentPhase": "02_verifier", "secret": "x"})

    detail = tools.job_detail("run_1")

    assert detail["status"] == "FAILED" and detail["blockedReason"] == "verifier"
    assert "secret" not in detail
    with pytest.raises(ToolError):
        tools.job_detail("../../etc")
