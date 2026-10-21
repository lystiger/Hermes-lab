import pytest

from agent_models import CLAUDE_EFFORTS, CLAUDE_MODELS, ModelRegistry
from runner.agents.claude import ClaudeAdapter


def test_each_supported_claude_model_offers_the_cli_effort_levels(tmp_path):
    registry = ModelRegistry(tmp_path / "agent_models.json")

    by_id = {m["id"]: m for m in registry.models("claude")}

    for model in CLAUDE_MODELS:
        assert by_id[model]["efforts"] == list(CLAUDE_EFFORTS)


def test_a_supported_effort_is_saved_and_an_unknown_one_is_refused(tmp_path):
    registry = ModelRegistry(tmp_path / "agent_models.json")

    registry.set("claude", CLAUDE_MODELS[1], "max")
    assert registry.configured("claude")["effort"] == "max"

    with pytest.raises(ValueError):
        registry.set("claude", CLAUDE_MODELS[1], "ultra")


def test_the_claude_command_passes_the_effort_only_when_set():
    with_effort = ClaudeAdapter().build_command("work", {"model": "claude-opus-5-5", "effort": "high"})
    without = ClaudeAdapter().build_command("work", {"model": "claude-opus-5-5"})

    assert with_effort[with_effort.index("--effort") + 1] == "high"
    assert "--effort" not in without
