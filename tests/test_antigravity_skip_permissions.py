"""A goal job can run Antigravity with --dangerously-skip-permissions; the default keeps the allowlist."""
from runtime.limits import RuntimeLimits
from jobs.job_launcher import JobLauncher
from runner.agents.antigravity import AntigravityAdapter


def actor_options(tmp_path, **meta):
    meta = {"target_repo": str(tmp_path), "worktree_root": str(tmp_path / "wt"),
            "runs_root": str(tmp_path / "runs"), **meta}
    _, actor, _ = JobLauncher()._goal_adapters("job_skip", meta, event_bridge=None, limits=RuntimeLimits())
    return actor.default_agent_options


def test_flag_reaches_agent_options(tmp_path):
    assert actor_options(tmp_path, agent_max_turns=20, antigravity_skip_permissions=True) == {
        "max_turns": 20, "dangerously_skip_permissions": True}


def test_default_keeps_permissions(tmp_path):
    assert "dangerously_skip_permissions" not in actor_options(tmp_path, agent_max_turns=20)


def test_antigravity_command_carries_the_flag():
    assert "--dangerously-skip-permissions" in AntigravityAdapter().build_command(
        "p", {"dangerously_skip_permissions": True})
