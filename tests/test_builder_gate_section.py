import json
from pathlib import Path
import pytest
from runtime.hermes_adapter import HermesActorAdapter, PROJECT_CHECKS_FILE
from runtime.task_graph import TaskNode


def declare_checks(root: Path, *checks):
    data = {"checks": list(checks)}
    (root / PROJECT_CHECKS_FILE).write_text(json.dumps(data), encoding="utf-8")


def test_builder_project_checks_section_direct(tmp_path):
    """Direct unit test of _builder_project_checks_section with checks, empty checks, and absent hermes.json."""
    adapter = HermesActorAdapter(target_repo=tmp_path, worktree_root=tmp_path / "wt", run_dir=tmp_path / "run")

    # 1. Absent hermes.json -> returns empty string
    assert adapter._builder_project_checks_section(tmp_path) == ""

    # 2. hermes.json with empty checks -> returns empty string
    declare_checks(tmp_path)
    assert adapter._builder_project_checks_section(tmp_path) == ""

    # 3. hermes.json with declared checks -> returns formatted section
    declare_checks(
        tmp_path,
        {"name": "unit", "command": "pytest tests/unit"},
        {"name": "lint", "command": "ruff check"},
    )
    section = adapter._builder_project_checks_section(tmp_path)
    assert "--- PROJECT CHECKS ---" in section
    assert "--- END PROJECT CHECKS ---" in section
    assert "Hermes does not run them for builders" in section
    assert "run them before finishing" in section
    assert "- unit: `pytest tests/unit`" in section
    assert "- lint: `ruff check`" in section

    # 4. Target subdir support
    sub = tmp_path / "service"
    sub.mkdir()
    declare_checks(sub, {"name": "sub-test", "command": "pytest"})
    adapter_sub = HermesActorAdapter(target_repo=tmp_path, target_subdir="service")
    sec_sub = adapter_sub._builder_project_checks_section(tmp_path)
    assert "- sub-test: `pytest`" in sec_sub


def test_builder_prompt_includes_declared_checks_section(tmp_path):
    """Builder prompt includes declared checks by name and command, states Hermes does not run them, asks agent to run them."""
    declare_checks(
        tmp_path,
        {"name": "unit-tests", "command": "pytest tests/unit"},
        {"name": "typecheck", "command": "mypy runtime"},
    )
    adapter = HermesActorAdapter(target_repo=tmp_path, worktree_root=tmp_path / "wt", run_dir=tmp_path / "run")
    task = TaskNode(
        task_id="t1_build",
        job_id="job_test",
        description="Implement user authentication.",
        attempt=0,
    )

    prompt = adapter._prepare_effective_prompt(task, "antigravity", "builder", worktree_path=tmp_path)

    assert "--- PROJECT CHECKS ---" in prompt
    assert "--- END PROJECT CHECKS ---" in prompt
    assert "Hermes does not run them for builders" in prompt
    assert "run them before finishing" in prompt
    assert "- unit-tests: `pytest tests/unit`" in prompt
    assert "- typecheck: `mypy runtime`" in prompt
    # Verifier section must NOT be present
    assert "--- CHECKS HERMES RAN ---" not in prompt


def test_hardener_prompt_includes_declared_checks_section(tmp_path):
    """Hardener prompt also receives the declared checks section."""
    declare_checks(
        tmp_path,
        {"name": "integration", "command": "pytest tests/integration"},
    )
    adapter = HermesActorAdapter(target_repo=tmp_path, worktree_root=tmp_path / "wt", run_dir=tmp_path / "run")
    task = TaskNode(
        task_id="t2_harden",
        job_id="job_test",
        description="Harden auth service edge cases.",
        attempt=0,
    )

    prompt = adapter._prepare_effective_prompt(task, "claude", "hardener", worktree_path=tmp_path)

    assert "--- PROJECT CHECKS ---" in prompt
    assert "--- END PROJECT CHECKS ---" in prompt
    assert "Hermes does not run them for builders" in prompt
    assert "run them before finishing" in prompt
    assert "- integration: `pytest tests/integration`" in prompt
    assert "--- CHECKS HERMES RAN ---" not in prompt


def test_builder_and_hardener_prompts_omit_section_when_hermes_json_absent(tmp_path):
    """When hermes.json is absent, builder and hardener prompts omit the section."""
    adapter = HermesActorAdapter(target_repo=tmp_path, worktree_root=tmp_path / "wt", run_dir=tmp_path / "run")
    task_builder = TaskNode(task_id="t1", job_id="job_test", description="Build something.", attempt=0)
    task_hardener = TaskNode(task_id="t2", job_id="job_test", description="Harden something.", attempt=0)

    prompt_builder = adapter._prepare_effective_prompt(task_builder, "antigravity", "builder", worktree_path=tmp_path)
    assert "--- PROJECT CHECKS ---" not in prompt_builder
    assert "Hermes does not run them for builders" not in prompt_builder

    prompt_hardener = adapter._prepare_effective_prompt(task_hardener, "claude", "hardener", worktree_path=tmp_path)
    assert "--- PROJECT CHECKS ---" not in prompt_hardener
    assert "Hermes does not run them for builders" not in prompt_hardener


def test_builder_and_hardener_prompts_omit_section_when_checks_empty(tmp_path):
    """When hermes.json declares no checks (empty list), builder and hardener prompts omit the section."""
    declare_checks(tmp_path)
    adapter = HermesActorAdapter(target_repo=tmp_path, worktree_root=tmp_path / "wt", run_dir=tmp_path / "run")
    task = TaskNode(task_id="t1", job_id="job_test", description="Build feature.", attempt=0)

    prompt_builder = adapter._prepare_effective_prompt(task, "antigravity", "builder", worktree_path=tmp_path)
    assert "--- PROJECT CHECKS ---" not in prompt_builder
    assert "Hermes does not run them for builders" not in prompt_builder

    prompt_hardener = adapter._prepare_effective_prompt(task, "claude", "hardener", worktree_path=tmp_path)
    assert "--- PROJECT CHECKS ---" not in prompt_hardener
    assert "Hermes does not run them for builders" not in prompt_hardener


def test_verifier_and_security_prompts_stay_unchanged(tmp_path):
    """Verifier and security prompts keep CHECKS HERMES RAN and do not receive the builder gate section."""
    declare_checks(
        tmp_path,
        {"name": "unit", "command": "echo 42 passed"},
    )
    adapter = HermesActorAdapter(target_repo=tmp_path, worktree_root=tmp_path / "wt", run_dir=tmp_path / "run")
    task_verifier = TaskNode(task_id="t3_verify", job_id="job_test", description="Verify work.", attempt=0)
    task_security = TaskNode(task_id="t4_sec", job_id="job_test", description="Security audit.", attempt=0)

    prompt_verifier = adapter._prepare_effective_prompt(task_verifier, "codex", "verifier", worktree_path=tmp_path)
    assert "--- CHECKS HERMES RAN ---" in prompt_verifier
    assert "42 passed" in prompt_verifier
    assert "--- PROJECT CHECKS ---" not in prompt_verifier
    assert "Hermes does not run them for builders" not in prompt_verifier

    prompt_security = adapter._prepare_effective_prompt(task_security, "codex", "security", worktree_path=tmp_path)
    assert "--- CHECKS HERMES RAN ---" in prompt_security
    assert "42 passed" in prompt_security
    assert "--- PROJECT CHECKS ---" not in prompt_security
    assert "Hermes does not run them for builders" not in prompt_security


def test_other_roles_omit_builder_checks_section(tmp_path):
    """Other roles (e.g. operative, researcher) do not receive the builder project checks section."""
    declare_checks(tmp_path, {"name": "unit", "command": "echo passed"})
    adapter = HermesActorAdapter(target_repo=tmp_path, worktree_root=tmp_path / "wt", run_dir=tmp_path / "run")
    task = TaskNode(task_id="t5", job_id="job_test", description="Plan the architecture.", attempt=0)

    prompt = adapter._prepare_effective_prompt(task, "planner", "operative", worktree_path=tmp_path)
    assert "--- PROJECT CHECKS ---" not in prompt
    assert "--- CHECKS HERMES RAN ---" not in prompt
