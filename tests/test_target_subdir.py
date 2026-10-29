"""target_subdir: agents and verification run in a subfolder; git stays at the repository root."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from runtime.hermes_adapter import HermesVerifierAdapter
from runtime.target_subdir import normalize_target_subdir, subdir_path
from runtime.verification import VerificationStatus


class TestNormalizeTargetSubdir(unittest.TestCase):
    def test_empty_and_dot_mean_repository_root(self):
        for value in (None, "", ".", "  ", "./"):
            self.assertEqual(normalize_target_subdir(value), "", repr(value))

    def test_trailing_and_leading_dot_slashes_are_dropped(self):
        self.assertEqual(normalize_target_subdir("console"), "console")
        self.assertEqual(normalize_target_subdir("console/"), "console")
        self.assertEqual(normalize_target_subdir("./console"), "console")
        self.assertEqual(normalize_target_subdir("apps/console"), "apps/console")

    def test_escapes_and_absolute_paths_are_rejected(self):
        for value in ("../console", "console/../../etc", "/etc", "C:\\console", "a\\b"):
            with self.assertRaises(ValueError, msg=value):
                normalize_target_subdir(value)

    def test_subdir_path_joins_only_when_set(self):
        root = Path("/tmp/wt")
        self.assertEqual(subdir_path(root, ""), root)
        self.assertEqual(subdir_path(root, "console"), root / "console")


class TestVerifierRunsInSubdir(unittest.IsolatedAsyncioTestCase):
    async def _verify(self, root, steps, target_subdir):
        adapter = HermesVerifierAdapter(
            verification_steps=steps,
            working_dir=root,
            target_subdir=target_subdir,
        )
        return await adapter.verify(job=SimpleNamespace(job_id="j"), graph=None, artifacts=[])

    async def test_default_step_cwd_is_the_subfolder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "console").mkdir()
            (root / "console" / "marker.txt").write_text("here")
            steps = [{"name": "marker", "command": ["sh", "-c", "test -f marker.txt"]}]

            res = await self._verify(root, steps, "console")

            self.assertEqual(res.status, VerificationStatus.PASSED)

    async def test_marker_only_at_root_fails_when_subdir_is_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "console").mkdir()
            (root / "marker.txt").write_text("root only")
            steps = [{"name": "marker", "command": ["sh", "-c", "test -f marker.txt"]}]

            res = await self._verify(root, steps, "console")

            self.assertNotEqual(res.status, VerificationStatus.PASSED)

    async def test_step_cwd_is_relative_to_the_subfolder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "console" / "frontend").mkdir(parents=True)
            (root / "console" / "frontend" / "marker.txt").write_text("here")
            steps = [{"name": "nested", "cwd": "frontend", "command": ["sh", "-c", "test -f marker.txt"]}]

            res = await self._verify(root, steps, "console")

            self.assertEqual(res.status, VerificationStatus.PASSED)

    async def test_empty_subdir_keeps_root_behaviour(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "marker.txt").write_text("root")
            steps = [{"name": "marker", "command": ["sh", "-c", "test -f marker.txt"]}]

            res = await self._verify(root, steps, "")

            self.assertEqual(res.status, VerificationStatus.PASSED)


def test_a_goal_job_verifies_with_the_subfolders_checks(tmp_path):
    import asyncio
    import json

    from jobs.job_launcher import JobLauncher
    from runtime.limits import RuntimeLimits

    (tmp_path / "integration" / "console").mkdir(parents=True)
    (tmp_path / "integration" / "console" / "hermes.json").write_text(
        json.dumps({"checks": [{"name": "console-check", "command": "exit 1"}]}))
    meta = {"target_repo": str(tmp_path), "worktree_root": str(tmp_path), "runs_root": str(tmp_path / "runs"),
            "target_subdir": "console"}
    _, _, verifier = JobLauncher()._goal_adapters("job_sub", meta, event_bridge=None, limits=RuntimeLimits())

    result = asyncio.run(verifier.verify(job=SimpleNamespace(job_id="job_sub"), graph=None, artifacts=[]))

    assert [c.name for c in result.checks] == ["console-check"]
