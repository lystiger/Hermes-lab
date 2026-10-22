import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_runner():
    spec = importlib.util.spec_from_file_location("run_hermes_sprint_security", ROOT / "runner" / "run-hermes-sprint.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner_module = load_runner()
Runner = runner_module.HermesSprintRunner


def bare_runner(tmp_path):
    runner = Runner.__new__(Runner)
    runner.worktree_root = tmp_path
    runner.limits = {"max_changed_files": 15}
    runner.logger = MagicMock()
    runner.validate_python_syntax = MagicMock()
    return runner


def test_security_is_a_known_read_only_role(tmp_path):
    runner = bare_runner(tmp_path)
    assert runner.resolve_phase_role({"role": "security"}) == "security"
    assert "security" in Runner.READ_ONLY_ROLES


def test_security_phase_may_not_change_product_files(tmp_path):
    runner = bare_runner(tmp_path)
    runner.inspect_changed_files = MagicMock(return_value=[" M app.py"])
    phase = {"name": "security-review", "role": "security", "worktree_dir": "security"}
    with pytest.raises(runner_module.SprintRunnerError) as err:
        runner._validate_phase_changes(phase)
    assert err.value.code == "FAILED_FORBIDDEN_CHANGES"


def test_security_phase_without_changes_passes_validation(tmp_path):
    runner = bare_runner(tmp_path)
    runner.inspect_changed_files = MagicMock(return_value=[])
    phase = {"name": "security-review", "role": "security", "worktree_dir": "security"}
    assert runner._validate_phase_changes(phase) == []
