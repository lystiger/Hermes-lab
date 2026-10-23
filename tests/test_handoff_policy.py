"""A phase's handoff file is evidence: the verifier may write it, and builders never commit it."""
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

from runtime.hermes_adapter import HermesActorAdapter


def _adapter(worktree_root: Path) -> HermesActorAdapter:
    adapter = HermesActorAdapter.__new__(HermesActorAdapter)
    adapter._git_lock = threading.RLock()
    adapter.worktree_root = worktree_root
    adapter.target_subdir = ""
    adapter._verify_execution_fence = lambda *args, **kwargs: None
    adapter._is_worktree_root = lambda path: True
    adapter.run_cmd = lambda cmd, cwd=None, check=True: subprocess.run(
        cmd, cwd=cwd, check=check, capture_output=True, text=True
    )
    return adapter


def _task(expected_handoff=None) -> SimpleNamespace:
    metadata = {"commit_message": "feat: test change"}
    if expected_handoff:
        metadata["expected_handoff"] = expected_handoff
    return SimpleNamespace(task_id="m_builder", description="test", metadata=metadata)


def test_exclude_handoff_keeps_product_changes_only():
    adapter = _adapter(Path("/unused"))
    changed = ["?? HANDOFF_BUILDER.md", " M runner/codex.py", "?? tests/test_new.py"]

    assert adapter._exclude_handoff(changed, _task("HANDOFF_BUILDER.md")) == [
        " M runner/codex.py",
        "?? tests/test_new.py",
    ]


def test_exclude_handoff_without_expected_handoff_keeps_everything():
    adapter = _adapter(Path("/unused"))
    changed = ["?? HANDOFF_CODEX.md", " M a.py"]

    assert adapter._exclude_handoff(changed, _task()) == changed


def test_builder_commit_stages_product_files_and_leaves_handoff_untracked(tmp_path):
    worktree = tmp_path / "builder"
    worktree.mkdir()
    git = lambda *args: subprocess.run(["git", *args], cwd=worktree, check=True, capture_output=True, text=True)
    git("init", "-q")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "test")
    (worktree / "seed.py").write_text("x = 1\n")
    git("add", "seed.py")
    git("commit", "-q", "-m", "seed")

    (worktree / "product.py").write_text("y = 2\n")
    (worktree / "HANDOFF_BUILDER.md").write_text("# handoff\n")

    adapter = _adapter(tmp_path / "no-integration")
    adapter._is_worktree_root = lambda path: Path(path) == worktree
    sha = adapter._commit_and_integrate_changes(worktree, _task("HANDOFF_BUILDER.md"), "builder")

    assert sha
    committed = git("show", "--name-only", "--format=", "HEAD").stdout.split()
    assert committed == ["product.py"]
    status = git("status", "--porcelain").stdout
    assert "?? HANDOFF_BUILDER.md" in status
