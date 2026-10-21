import json

import pytest

from research import tools_server
from research.tools_server import ResearchTools, TOOL_NAMES, handle

GOOD_FINDING = {"claim": "a claim", "source_url": "https://pypi.org/project/x/", "retrieved": "2026-10-21"}


@pytest.fixture
def tools(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("pytest\n")
    sources = tmp_path / "sources.json"
    sources.write_text("[]")
    return ResearchTools(tmp_path, requirements, sources, tmp_path / "state")


def _call(tools, name, arguments):
    return handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": name, "arguments": arguments}}, tools)["result"]


def test_the_server_offers_exactly_the_three_tools(tools):
    names = [t["name"] for t in handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, tools)["result"]["tools"]]

    assert names == list(TOOL_NAMES) == ["watch_releases", "research_save", "source_check"]


def test_notifications_get_no_answer(tools):
    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, tools) is None


def test_watch_releases_runs_the_budgeted_watch(tools, monkeypatch):
    monkeypatch.setattr(tools_server, "run", lambda *a, **k: {"dependencies": [], "sources": [], "requests_used": 0})

    result = _call(tools, "watch_releases", {})

    assert result["isError"] is False and "requests_used" in result["content"][0]["text"]


def test_research_save_writes_a_file_in_lysstack(tools, tmp_path):
    result = _call(tools, "research_save", {"topic": "tool-check", "findings": [GOOD_FINDING]})

    assert result["isError"] is False
    assert (tmp_path / "research" / "tool-check.md").exists()


def test_research_save_refuses_a_finding_without_a_source(tools):
    result = _call(tools, "research_save", {"topic": "no-source", "findings": [{"claim": "x"}]})

    assert result["isError"] is True


def test_source_check_refuses_a_host_off_the_allowlist(tools):
    result = _call(tools, "source_check", {"url": "https://example.com/x", "quote": "q"})

    payload = json.loads(result["content"][0]["text"])
    assert payload["status"] == "UNPROVEN"


def test_unknown_tools_are_refused(tools):
    assert _call(tools, "deploy_now", {})["isError"] is True
