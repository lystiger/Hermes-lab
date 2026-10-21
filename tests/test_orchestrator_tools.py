import json
import subprocess

import pytest

from orchestrator import chat as chat_module
from orchestrator import tools_server
from orchestrator.chat import ClaudeChatProvider
from orchestrator.tools_server import LysStackTools, handle


@pytest.fixture
def root(tmp_path):
    lysstack = tmp_path / "LysStack"
    (lysstack / "operating_system").mkdir(parents=True)
    (lysstack / "operating_system" / "current_focus.md").write_text("focus\n")
    (lysstack / "AGENTS.md").write_text("# rules\n")
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
    assert names == ["lysstack_list", "lysstack_read", "hermes_jobs", "hermes_capacity", "draft_save"]
    assert set(names) == set(tools_server.TOOL_NAMES)


def test_notifications_get_no_answer(root):
    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, LysStackTools(root)) is None


def test_list_and_read_stay_inside_lysstack(root):
    tools = LysStackTools(root)

    assert _call(tools, "lysstack_list", {"scope": "operating_system"})["content"][0]["text"] == \
        json.dumps(["operating_system/current_focus.md"], indent=2)
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
                                         "drafts": tmp_path / "drafts"})

    provider.reply("SYS", [{"role": "user", "content": "hi"}], "claude-haiku-5-5", None)

    argv = seen["argv"]
    assert "--strict-mcp-config" in argv
    allowed = argv[argv.index("--allowedTools") + 1:]
    assert allowed == [f"mcp__lysstack__{n}" for n in tools_server.TOOL_NAMES]
    assert not any(tool in argv for tool in ("Bash", "Edit", "Write"))
    server = seen["config"]["mcpServers"]["lysstack"]
    assert server["args"][-2:] == ["--drafts", str(tmp_path / "drafts")]
    assert server["env"]["PYTHONPATH"] == str(root)
