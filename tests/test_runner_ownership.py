import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from unittest.mock import MagicMock, patch

# Dynamically import runner/run-hermes-sprint.py
runner_path = Path(__file__).resolve().parent.parent / "runner" / "run-hermes-sprint.py"
spec = importlib.util.spec_from_file_location("run_hermes_sprint", runner_path)
runner_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner_module)

HermesSprintRunner = runner_module.HermesSprintRunner
SprintRunnerError = runner_module.SprintRunnerError


class TestOwnershipSpecValidation(unittest.TestCase):
    """Contract tests for Rule 1, Rule 2, and Rule 3 spec-level validations."""

    def setUp(self):
        self.logging_patch = patch.object(
            HermesSprintRunner, "_setup_logging", return_value=MagicMock()
        )
        self.logging_patch.start()
        self.addCleanup(self.logging_patch.stop)

    def write_spec(self, path, phases, **overrides):
        specification = {
            "sprint_id": "ownership-spec-test",
            "control_root": str(runner_path.parent.parent),
            "target_repo": str(runner_path.parent.parent),
            "worktree_root": str(path.parent / "worktrees"),
            "runs_root": str(path.parent / "runs"),
            "phases": phases,
            **overrides,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(specification), encoding="utf-8")
        return path

    def make_phase(self, name="builder", role="builder", **kwargs):
        phase = {
            "name": name,
            "role": role,
            "agent": "codex",
            "worktree_dir": name,
            "branch": f"s07/{name}",
            "prompt_file": "prompts/s02-agy.md",
            "expected_handoff": "HANDOFF.md",
            "commit_message": f"test: {name}",
        }
        phase.update(kwargs)
        return phase

    def make_runner(self, root, phases):
        spec_path = self.write_spec(root / "spec.json", phases)
        runner = HermesSprintRunner(spec_path, dry_run=True, skip_agent_exec=True)
        runner.validate_execution_plan()
        return runner

    # -------------------------------------------------------------------------
    # Valid Specification Cases (Rule 1, Rule 2, Rule 3)
    # -------------------------------------------------------------------------

    def test_valid_owned_paths_single_prefix(self):
        """Rule 1: A phase may declare owned_paths with a valid relative prefix."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase = self.make_phase(owned_paths=["backend/"])
            runner = self.make_runner(root, [phase])
            self.assertEqual(runner.spec["phases"][0]["owned_paths"], ["backend/"])

    def test_valid_owned_paths_multiple_prefixes(self):
        """Rule 1: Multiple non-empty relative path prefixes are valid."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase = self.make_phase(
                owned_paths=["backend/", "frontend/app/", "docs/api/"]
            )
            runner = self.make_runner(root, [phase])
            self.assertEqual(
                runner.spec["phases"][0]["owned_paths"],
                ["backend/", "frontend/app/", "docs/api/"],
            )

    def test_valid_owned_paths_nested_subdirectories(self):
        """Rule 1: Deeply nested relative path prefixes are valid."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase = self.make_phase(
                owned_paths=["src/services/auth/v2/", "packages/client/lib/"]
            )
            runner = self.make_runner(root, [phase])
            self.assertEqual(
                runner.spec["phases"][0]["owned_paths"],
                ["src/services/auth/v2/", "packages/client/lib/"],
            )

    def test_valid_owned_paths_without_trailing_slash(self):
        """Rule 1: Relative directory prefixes without trailing slashes are valid."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase = self.make_phase(owned_paths=["backend", "frontend/app"])
            runner = self.make_runner(root, [phase])
            self.assertEqual(
                [p.rstrip("/") for p in runner.spec["phases"][0]["owned_paths"]],
                ["backend", "frontend/app"],
            )

    def test_valid_owned_paths_without_parallel_group(self):
        """Rule 1 & Rule 3: A phase may declare owned_paths without a parallel_group."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase = self.make_phase(owned_paths=["backend/"])
            runner = self.make_runner(root, [phase])
            self.assertNotIn("parallel_group", runner.spec["phases"][0])

    def test_valid_parallel_group_non_overlapping(self):
        """Rule 2: Phases in the same parallel_group with disjoint owned_paths are valid."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase1 = self.make_phase(
                name="builder-backend",
                owned_paths=["backend/"],
                parallel_group="group-alpha",
            )
            phase2 = self.make_phase(
                name="builder-frontend",
                owned_paths=["frontend/"],
                parallel_group="group-alpha",
            )
            runner = self.make_runner(root, [phase1, phase2])
            self.assertEqual(len(runner.spec["phases"]), 2)

    def test_valid_parallel_group_boundary_backend_and_backend2(self):
        """Rule 2 Boundary: backend/ does NOT overlap backend2/ at a / boundary."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase1 = self.make_phase(
                name="builder-backend",
                owned_paths=["backend/"],
                parallel_group="core-group",
            )
            phase2 = self.make_phase(
                name="builder-backend2",
                owned_paths=["backend2/"],
                parallel_group="core-group",
            )
            runner = self.make_runner(root, [phase1, phase2])
            self.assertEqual(len(runner.spec["phases"]), 2)

    def test_valid_parallel_group_boundary_without_trailing_slashes(self):
        """Rule 2 Boundary: backend does not overlap backend2 without trailing slashes."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase1 = self.make_phase(
                name="builder-backend",
                owned_paths=["backend"],
                parallel_group="core-group",
            )
            phase2 = self.make_phase(
                name="builder-backend2",
                owned_paths=["backend2"],
                parallel_group="core-group",
            )
            runner = self.make_runner(root, [phase1, phase2])
            self.assertEqual(len(runner.spec["phases"]), 2)

    def test_valid_different_parallel_groups_may_share_paths(self):
        """Rule 2: Phases in different parallel_groups may have overlapping owned_paths."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase1 = self.make_phase(
                name="builder-1",
                owned_paths=["backend/"],
                parallel_group="group-1",
            )
            phase2 = self.make_phase(
                name="builder-2",
                owned_paths=["backend/"],
                parallel_group="group-2",
            )
            runner = self.make_runner(root, [phase1, phase2])
            self.assertEqual(len(runner.spec["phases"]), 2)

    # -------------------------------------------------------------------------
    # Invalid Rule 1 Cases (owned_paths)
    # -------------------------------------------------------------------------

    def test_invalid_owned_paths_not_a_list(self):
        """Rule 1: owned_paths must be a list; non-list types are invalid."""
        invalid_types = [
            "backend/",
            123,
            True,
            {"path": "backend/"},
        ]
        for index, bad_value in enumerate(invalid_types):
            with self.subTest(bad_value=bad_value):
                with tempfile.TemporaryDirectory() as temporary_dir:
                    root = Path(temporary_dir)
                    phase = self.make_phase(owned_paths=bad_value)
                    with self.assertRaises(SprintRunnerError) as ctx:
                        self.make_runner(root / str(index), [phase])
                    self.assertTrue(
                        ctx.exception.code.startswith("FAILED_")
                        and any(
                            k in ctx.exception.code
                            for k in ("OWNERSHIP", "OWNED", "PATH", "SPEC")
                        ),
                        f"Unexpected error code: {ctx.exception.code}",
                    )

    def test_invalid_owned_paths_empty_list(self):
        """Rule 1: owned_paths cannot be an empty list."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase = self.make_phase(owned_paths=[])
            with self.assertRaises(SprintRunnerError) as ctx:
                self.make_runner(root, [phase])
            self.assertTrue(
                ctx.exception.code.startswith("FAILED_")
                and any(
                    k in ctx.exception.code
                    for k in ("OWNERSHIP", "OWNED", "PATH", "SPEC")
                ),
                f"Unexpected error code: {ctx.exception.code}",
            )

    def test_invalid_owned_paths_empty_string(self):
        """Rule 1: Empty strings inside owned_paths are invalid."""
        cases = [
            [""],
            ["backend/", ""],
            ["", "frontend/"],
        ]
        for index, paths in enumerate(cases):
            with self.subTest(paths=paths):
                with tempfile.TemporaryDirectory() as temporary_dir:
                    root = Path(temporary_dir)
                    phase = self.make_phase(owned_paths=paths)
                    with self.assertRaises(SprintRunnerError) as ctx:
                        self.make_runner(root / str(index), [phase])
                    self.assertTrue(
                        ctx.exception.code.startswith("FAILED_")
                        and any(
                            k in ctx.exception.code
                            for k in ("OWNERSHIP", "OWNED", "PATH", "SPEC")
                        ),
                        f"Unexpected error code: {ctx.exception.code}",
                    )

    def test_invalid_owned_paths_whitespace_string(self):
        """Rule 1: Whitespace-only strings inside owned_paths are invalid."""
        cases = [
            ["   "],
            ["\t"],
            ["backend/", "  \n  "],
        ]
        for index, paths in enumerate(cases):
            with self.subTest(paths=paths):
                with tempfile.TemporaryDirectory() as temporary_dir:
                    root = Path(temporary_dir)
                    phase = self.make_phase(owned_paths=paths)
                    with self.assertRaises(SprintRunnerError) as ctx:
                        self.make_runner(root / str(index), [phase])
                    self.assertTrue(
                        ctx.exception.code.startswith("FAILED_")
                        and any(
                            k in ctx.exception.code
                            for k in ("OWNERSHIP", "OWNED", "PATH", "SPEC")
                        ),
                        f"Unexpected error code: {ctx.exception.code}",
                    )

    def test_invalid_owned_paths_absolute_path_posix(self):
        """Rule 1: Absolute POSIX paths inside owned_paths are invalid."""
        cases = [
            ["/backend/"],
            ["/etc/passwd"],
            ["/tmp/project/app/"],
            ["backend/", "/frontend/"],
        ]
        for index, paths in enumerate(cases):
            with self.subTest(paths=paths):
                with tempfile.TemporaryDirectory() as temporary_dir:
                    root = Path(temporary_dir)
                    phase = self.make_phase(owned_paths=paths)
                    with self.assertRaises(SprintRunnerError) as ctx:
                        self.make_runner(root / str(index), [phase])
                    self.assertTrue(
                        ctx.exception.code.startswith("FAILED_")
                        and any(
                            k in ctx.exception.code
                            for k in ("OWNERSHIP", "OWNED", "PATH", "SPEC")
                        ),
                        f"Unexpected error code: {ctx.exception.code}",
                    )

    def test_invalid_owned_paths_absolute_path_windows(self):
        """Rule 1: Absolute Windows paths with drive anchors are invalid."""
        cases = [
            ["C:/backend/"],
            ["C:\\backend\\"],
            ["D:/app/services/"],
        ]
        for index, paths in enumerate(cases):
            with self.subTest(paths=paths):
                with tempfile.TemporaryDirectory() as temporary_dir:
                    root = Path(temporary_dir)
                    phase = self.make_phase(owned_paths=paths)
                    with self.assertRaises(SprintRunnerError) as ctx:
                        self.make_runner(root / str(index), [phase])
                    self.assertTrue(
                        ctx.exception.code.startswith("FAILED_")
                        and any(
                            k in ctx.exception.code
                            for k in ("OWNERSHIP", "OWNED", "PATH", "SPEC")
                        ),
                        f"Unexpected error code: {ctx.exception.code}",
                    )

    def test_invalid_owned_paths_parent_traversal(self):
        """Rule 1: .. segments inside owned_paths are invalid."""
        cases = [
            [".."],
            ["../outside/"],
            ["backend/../outside/"],
            ["backend/sub/../../escaped/"],
            ["sub/.."],
        ]
        for index, paths in enumerate(cases):
            with self.subTest(paths=paths):
                with tempfile.TemporaryDirectory() as temporary_dir:
                    root = Path(temporary_dir)
                    phase = self.make_phase(owned_paths=paths)
                    with self.assertRaises(SprintRunnerError) as ctx:
                        self.make_runner(root / str(index), [phase])
                    self.assertTrue(
                        ctx.exception.code.startswith("FAILED_")
                        and any(
                            k in ctx.exception.code
                            for k in ("OWNERSHIP", "OWNED", "PATH", "SPEC")
                        ),
                        f"Unexpected error code: {ctx.exception.code}",
                    )

    def test_invalid_owned_paths_non_string_elements(self):
        """Rule 1: Non-string items inside owned_paths list are invalid."""
        cases = [
            [123],
            [None],
            [True],
            [{"path": "backend/"}],
            ["backend/", 42],
        ]
        for index, paths in enumerate(cases):
            with self.subTest(paths=paths):
                with tempfile.TemporaryDirectory() as temporary_dir:
                    root = Path(temporary_dir)
                    phase = self.make_phase(owned_paths=paths)
                    with self.assertRaises(SprintRunnerError) as ctx:
                        self.make_runner(root / str(index), [phase])
                    self.assertTrue(
                        ctx.exception.code.startswith("FAILED_")
                        and any(
                            k in ctx.exception.code
                            for k in ("OWNERSHIP", "OWNED", "PATH", "SPEC")
                        ),
                        f"Unexpected error code: {ctx.exception.code}",
                    )

    # -------------------------------------------------------------------------
    # Invalid Rule 2 Cases (parallel_group type and empty string)
    # -------------------------------------------------------------------------

    def test_invalid_parallel_group_not_a_string(self):
        """Rule 2: parallel_group must be a string."""
        invalid_groups = [
            123,
            True,
            ["group"],
            {"name": "group"},
        ]
        for index, bad_group in enumerate(invalid_groups):
            with self.subTest(bad_group=bad_group):
                with tempfile.TemporaryDirectory() as temporary_dir:
                    root = Path(temporary_dir)
                    phase = self.make_phase(
                        owned_paths=["backend/"],
                        parallel_group=bad_group,
                    )
                    with self.assertRaises(SprintRunnerError) as ctx:
                        self.make_runner(root / str(index), [phase])
                    self.assertTrue(
                        ctx.exception.code.startswith("FAILED_")
                        and any(
                            k in ctx.exception.code
                            for k in ("PARALLEL", "GROUP", "SPEC", "OWNERSHIP")
                        ),
                        f"Unexpected error code: {ctx.exception.code}",
                    )

    def test_invalid_parallel_group_empty_string(self):
        """Rule 2: parallel_group cannot be empty or whitespace-only."""
        invalid_groups = ["", "   ", "\t"]
        for index, bad_group in enumerate(invalid_groups):
            with self.subTest(bad_group=bad_group):
                with tempfile.TemporaryDirectory() as temporary_dir:
                    root = Path(temporary_dir)
                    phase = self.make_phase(
                        owned_paths=["backend/"],
                        parallel_group=bad_group,
                    )
                    with self.assertRaises(SprintRunnerError) as ctx:
                        self.make_runner(root / str(index), [phase])
                    self.assertTrue(
                        ctx.exception.code.startswith("FAILED_")
                        and any(
                            k in ctx.exception.code
                            for k in ("PARALLEL", "GROUP", "SPEC", "OWNERSHIP")
                        ),
                        f"Unexpected error code: {ctx.exception.code}",
                    )

    # -------------------------------------------------------------------------
    # Invalid Rule 3 Cases (parallel_group requires owned_paths)
    # -------------------------------------------------------------------------

    def test_invalid_parallel_group_missing_owned_paths(self):
        """Rule 3: A phase declaring parallel_group must also declare owned_paths."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase = self.make_phase(parallel_group="group-backend")
            # owned_paths is omitted
            with self.assertRaises(SprintRunnerError) as ctx:
                self.make_runner(root, [phase])
            self.assertTrue(
                ctx.exception.code.startswith("FAILED_")
                and any(
                    k in ctx.exception.code
                    for k in ("OWNERSHIP", "OWNED", "PARALLEL", "GROUP", "SPEC")
                ),
                f"Unexpected error code: {ctx.exception.code}",
            )

    def test_invalid_parallel_group_none_owned_paths(self):
        """Rule 3: parallel_group with owned_paths=None is invalid."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase = self.make_phase(
                parallel_group="group-backend",
                owned_paths=None,
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                self.make_runner(root, [phase])
            self.assertTrue(
                ctx.exception.code.startswith("FAILED_")
                and any(
                    k in ctx.exception.code
                    for k in ("OWNERSHIP", "OWNED", "PARALLEL", "GROUP", "SPEC")
                ),
                f"Unexpected error code: {ctx.exception.code}",
            )

    def test_invalid_parallel_group_one_phase_missing_owned_paths(self):
        """Rule 3: In a group, every phase must declare owned_paths."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase1 = self.make_phase(
                name="p1",
                parallel_group="group-shared",
                owned_paths=["backend/"],
            )
            phase2 = self.make_phase(
                name="p2",
                parallel_group="group-shared",
                # missing owned_paths
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                self.make_runner(root, [phase1, phase2])
            self.assertTrue(
                ctx.exception.code.startswith("FAILED_")
                and any(
                    k in ctx.exception.code
                    for k in ("OWNERSHIP", "OWNED", "PARALLEL", "GROUP", "SPEC")
                ),
                f"Unexpected error code: {ctx.exception.code}",
            )

    # -------------------------------------------------------------------------
    # Invalid Rule 2 Cases (Overlapping owned_paths in shared parallel_group)
    # -------------------------------------------------------------------------

    def test_invalid_parallel_group_identical_prefixes(self):
        """Rule 2: Phases in the same parallel_group cannot have identical owned_paths."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase1 = self.make_phase(
                name="p1",
                owned_paths=["backend/"],
                parallel_group="group-alpha",
            )
            phase2 = self.make_phase(
                name="p2",
                owned_paths=["backend/"],
                parallel_group="group-alpha",
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                self.make_runner(root, [phase1, phase2])
            self.assertTrue(
                ctx.exception.code.startswith("FAILED_")
                and any(
                    k in ctx.exception.code
                    for k in ("PARALLEL", "GROUP", "OVERLAP", "OWNERSHIP", "SPEC")
                ),
                f"Unexpected error code: {ctx.exception.code}",
            )

    def test_invalid_parallel_group_identical_prefixes_slash_variation(self):
        """Rule 2: backend and backend/ represent the same prefix and overlap."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase1 = self.make_phase(
                name="p1",
                owned_paths=["backend"],
                parallel_group="group-alpha",
            )
            phase2 = self.make_phase(
                name="p2",
                owned_paths=["backend/"],
                parallel_group="group-alpha",
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                self.make_runner(root, [phase1, phase2])
            self.assertTrue(
                ctx.exception.code.startswith("FAILED_")
                and any(
                    k in ctx.exception.code
                    for k in ("PARALLEL", "GROUP", "OVERLAP", "OWNERSHIP", "SPEC")
                ),
                f"Unexpected error code: {ctx.exception.code}",
            )

    def test_invalid_parallel_group_parent_child_slash_boundary(self):
        """Rule 2: backend/ overlaps backend/app/ at a / boundary."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase1 = self.make_phase(
                name="p1",
                owned_paths=["backend/"],
                parallel_group="shared-workers",
            )
            phase2 = self.make_phase(
                name="p2",
                owned_paths=["backend/app/"],
                parallel_group="shared-workers",
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                self.make_runner(root, [phase1, phase2])
            self.assertTrue(
                ctx.exception.code.startswith("FAILED_")
                and any(
                    k in ctx.exception.code
                    for k in ("PARALLEL", "GROUP", "OVERLAP", "OWNERSHIP", "SPEC")
                ),
                f"Unexpected error code: {ctx.exception.code}",
            )

    def test_invalid_parallel_group_child_parent_slash_boundary(self):
        """Rule 2: backend/app/ overlaps backend/ regardless of phase declaration order."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase1 = self.make_phase(
                name="p1",
                owned_paths=["backend/app/"],
                parallel_group="shared-workers",
            )
            phase2 = self.make_phase(
                name="p2",
                owned_paths=["backend/"],
                parallel_group="shared-workers",
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                self.make_runner(root, [phase1, phase2])
            self.assertTrue(
                ctx.exception.code.startswith("FAILED_")
                and any(
                    k in ctx.exception.code
                    for k in ("PARALLEL", "GROUP", "OVERLAP", "OWNERSHIP", "SPEC")
                ),
                f"Unexpected error code: {ctx.exception.code}",
            )

    def test_invalid_parallel_group_deep_child_overlap(self):
        """Rule 2: backend/ overlaps deeply nested backend/services/auth/api/."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase1 = self.make_phase(
                name="p1",
                owned_paths=["backend/"],
                parallel_group="shared-workers",
            )
            phase2 = self.make_phase(
                name="p2",
                owned_paths=["backend/services/auth/api/"],
                parallel_group="shared-workers",
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                self.make_runner(root, [phase1, phase2])
            self.assertTrue(
                ctx.exception.code.startswith("FAILED_")
                and any(
                    k in ctx.exception.code
                    for k in ("PARALLEL", "GROUP", "OVERLAP", "OWNERSHIP", "SPEC")
                ),
                f"Unexpected error code: {ctx.exception.code}",
            )

    def test_invalid_parallel_group_multi_path_partial_overlap(self):
        """Rule 2: Partial overlap among multiple declared paths must be rejected."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase1 = self.make_phase(
                name="p1",
                owned_paths=["frontend/", "backend/api/"],
                parallel_group="shared-workers",
            )
            phase2 = self.make_phase(
                name="p2",
                owned_paths=["docs/", "backend/"],
                parallel_group="shared-workers",
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                self.make_runner(root, [phase1, phase2])
            self.assertTrue(
                ctx.exception.code.startswith("FAILED_")
                and any(
                    k in ctx.exception.code
                    for k in ("PARALLEL", "GROUP", "OVERLAP", "OWNERSHIP", "SPEC")
                ),
                f"Unexpected error code: {ctx.exception.code}",
            )

    def test_invalid_parallel_group_three_phases_pairwise_overlap(self):
        """Rule 2: Overlap between 1st and 3rd phase in a 3-phase group is rejected."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            phase1 = self.make_phase(
                name="p1",
                owned_paths=["backend/"],
                parallel_group="pool-1",
            )
            phase2 = self.make_phase(
                name="p2",
                owned_paths=["frontend/"],
                parallel_group="pool-1",
            )
            phase3 = self.make_phase(
                name="p3",
                owned_paths=["backend/app/"],
                parallel_group="pool-1",
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                self.make_runner(root, [phase1, phase2, phase3])
            self.assertTrue(
                ctx.exception.code.startswith("FAILED_")
                and any(
                    k in ctx.exception.code
                    for k in ("PARALLEL", "GROUP", "OVERLAP", "OWNERSHIP", "SPEC")
                ),
                f"Unexpected error code: {ctx.exception.code}",
            )


class TestBuilderOwnershipEnforcement(unittest.TestCase):
    """Contract tests for Rule 4 builder ownership enforcement during execution."""

    def setUp(self):
        self.logging_patch = patch.object(
            HermesSprintRunner, "_setup_logging", return_value=MagicMock()
        )
        self.logging_patch.start()
        self.addCleanup(self.logging_patch.stop)

    def make_phase_runner(
        self,
        root,
        role="builder",
        changed_files=None,
        owned_paths=None,
        parallel_group=None,
        include_role=True,
    ):
        phase = {
            "name": "builder-ownership-phase",
            "agent": "codex",
            "worktree_dir": "worker",
            "branch": "s07/worker",
            "prompt_file": "prompts/s02-agy.md",
            "expected_handoff": "HANDOFF.md",
            "commit_message": "test: ownership phase execution",
        }
        if include_role:
            phase["role"] = role
        if owned_paths is not None:
            phase["owned_paths"] = owned_paths
        if parallel_group is not None:
            phase["parallel_group"] = parallel_group

        spec_file = root / "spec.json"
        spec_content = {
            "sprint_id": "ownership-enforcement-run",
            "control_root": str(runner_path.parent.parent),
            "target_repo": str(runner_path.parent.parent),
            "target_branch": "s07/integration",
            "worktree_root": str(root / "worktrees"),
            "runs_root": str(root / "runs"),
            "phases": [phase],
        }
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text(json.dumps(spec_content), encoding="utf-8")

        runner = HermesSprintRunner(
            spec_path=spec_file,
            skip_agent_exec=True,
        )
        runner.worktree_root = root / "worktrees"
        (runner.worktree_root / "worker").mkdir(parents=True, exist_ok=True)
        (runner.worktree_root / "integration").mkdir(parents=True, exist_ok=True)

        runner._prepare_handoff_path = MagicMock(
            return_value=(runner.worktree_root / "worker" / "HANDOFF.md", None)
        )
        runner._restore_handoff_path = MagicMock()
        runner.capture_handoff = MagicMock()
        runner.inspect_changed_files = MagicMock(
            return_value=changed_files if changed_files is not None else []
        )
        runner.validate_python_syntax = MagicMock()

        def command_result(command, **kwargs):
            stdout = "abc123\n" if command[:3] == ["git", "rev-parse", "HEAD"] else ""
            return subprocess.CompletedProcess(command, 0, stdout, "")

        runner.run_cmd = MagicMock(side_effect=command_result)
        return runner, phase

    # -------------------------------------------------------------------------
    # Rule 4 Violations (Must fail with FAILED_OUTSIDE_OWNERSHIP)
    # -------------------------------------------------------------------------

    def test_builder_fails_when_changing_file_outside_owned_paths(self):
        """Rule 4: Builder modifying a file outside owned_paths fails with FAILED_OUTSIDE_OWNERSHIP."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                role="builder",
                changed_files=[" M frontend/app.js"],
                owned_paths=["backend/"],
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                runner.execute_phase(phase)

            self.assertEqual(ctx.exception.code, "FAILED_OUTSIDE_OWNERSHIP")
            self.assertIn("frontend/app.js", ctx.exception.message)

    def test_builder_fails_when_any_changed_file_is_outside_owned_paths(self):
        """Rule 4: Failure names the outside file even if another change was within ownership."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                role="builder",
                changed_files=[" M backend/api.py", " M docs/readme.txt"],
                owned_paths=["backend/"],
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                runner.execute_phase(phase)

            self.assertEqual(ctx.exception.code, "FAILED_OUTSIDE_OWNERSHIP")
            self.assertIn("docs/readme.txt", ctx.exception.message)

    def test_builder_fails_on_root_file_when_subpath_owned(self):
        """Rule 4: Root-level files are outside prefix backend/ and must fail."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                role="builder",
                changed_files=[" M README.md"],
                owned_paths=["backend/"],
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                runner.execute_phase(phase)

            self.assertEqual(ctx.exception.code, "FAILED_OUTSIDE_OWNERSHIP")
            self.assertIn("README.md", ctx.exception.message)

    def test_builder_fails_on_boundary_backend2_file(self):
        """Rule 4 Boundary: backend2/api.py is outside backend/ and must fail."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                role="builder",
                changed_files=[" M backend2/api.py"],
                owned_paths=["backend/"],
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                runner.execute_phase(phase)

            self.assertEqual(ctx.exception.code, "FAILED_OUTSIDE_OWNERSHIP")
            self.assertIn("backend2/api.py", ctx.exception.message)

    def test_builder_fails_when_file_outside_multiple_owned_prefixes(self):
        """Rule 4: A file outside all declared prefixes fails with FAILED_OUTSIDE_OWNERSHIP."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                role="builder",
                changed_files=[" M config/database.yml"],
                owned_paths=["backend/", "frontend/app/"],
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                runner.execute_phase(phase)

            self.assertEqual(ctx.exception.code, "FAILED_OUTSIDE_OWNERSHIP")
            self.assertIn("config/database.yml", ctx.exception.message)

    def test_builder_fails_on_parent_directory_file(self):
        """Rule 4: A phase owning backend/app/ cannot modify backend/main.py."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                role="builder",
                changed_files=[" M backend/main.py"],
                owned_paths=["backend/app/"],
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                runner.execute_phase(phase)

            self.assertEqual(ctx.exception.code, "FAILED_OUTSIDE_OWNERSHIP")
            self.assertIn("backend/main.py", ctx.exception.message)

    def test_builder_fails_on_untracked_file_outside_ownership(self):
        """Rule 4: Untracked files outside owned_paths fail with FAILED_OUTSIDE_OWNERSHIP."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                role="builder",
                changed_files=["?? scratch/test_output.log"],
                owned_paths=["backend/"],
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                runner.execute_phase(phase)

            self.assertEqual(ctx.exception.code, "FAILED_OUTSIDE_OWNERSHIP")
            self.assertIn("scratch/test_output.log", ctx.exception.message)

    def test_builder_fails_on_added_file_outside_ownership(self):
        """Rule 4: Staged newly added files outside owned_paths fail."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                role="builder",
                changed_files=["A  services/external.py"],
                owned_paths=["backend/"],
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                runner.execute_phase(phase)

            self.assertEqual(ctx.exception.code, "FAILED_OUTSIDE_OWNERSHIP")
            self.assertIn("services/external.py", ctx.exception.message)

    def test_builder_outside_ownership_updates_run_summary_status(self):
        """Rule 4: runner.execute() updates summary status to FAILED_OUTSIDE_OWNERSHIP."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                role="builder",
                changed_files=[" M outside/file.txt"],
                owned_paths=["backend/"],
            )
            runner.prepare_environment = MagicMock()
            runner.run_verification = MagicMock()
            runner.run_tests_in_venv = MagicMock()
            runner.finalize = MagicMock()

            success = runner.execute()
            self.assertFalse(success)
            self.assertEqual(runner.run_summary["status"], "FAILED_OUTSIDE_OWNERSHIP")

    # -------------------------------------------------------------------------
    # Rule 4 Success Cases (Changes within owned_paths)
    # -------------------------------------------------------------------------

    def test_builder_succeeds_when_all_changes_inside_owned_paths(self):
        """Rule 4: Builder modifying only files inside owned_paths commits and integrates."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                role="builder",
                changed_files=[" M backend/api.py", " A backend/models.py"],
                owned_paths=["backend/"],
            )
            runner.execute_phase(phase)

            commands = [call.args[0] for call in runner.run_cmd.call_args_list]
            self.assertIn(["git", "add", "."], commands)
            self.assertTrue(any(cmd[:2] == ["git", "commit"] for cmd in commands))
            self.assertTrue(any(cmd[:2] == ["git", "merge"] for cmd in commands))
            self.assertTrue(runner.run_summary["phases"][0]["integrated"])
            self.assertEqual(runner.run_summary["phases"][0]["status"], "SUCCESS")

    def test_builder_succeeds_with_multiple_owned_paths(self):
        """Rule 4: Builder modifying files across multiple declared prefixes succeeds."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                role="builder",
                changed_files=[
                    " M backend/api.py",
                    " M frontend/app/view.tsx",
                ],
                owned_paths=["backend/", "frontend/app/"],
            )
            runner.execute_phase(phase)

            commands = [call.args[0] for call in runner.run_cmd.call_args_list]
            self.assertIn(["git", "add", "."], commands)
            self.assertTrue(any(cmd[:2] == ["git", "commit"] for cmd in commands))
            self.assertTrue(any(cmd[:2] == ["git", "merge"] for cmd in commands))
            self.assertTrue(runner.run_summary["phases"][0]["integrated"])

    def test_builder_succeeds_with_deeply_nested_file_inside_owned_prefix(self):
        """Rule 4: Files in subdirectories of owned prefix succeed."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                role="builder",
                changed_files=[" M backend/sub/controllers/v1/auth.py"],
                owned_paths=["backend/"],
            )
            runner.execute_phase(phase)
            self.assertTrue(runner.run_summary["phases"][0]["integrated"])


class TestOwnershipLegacyAndVerifierRules(unittest.TestCase):
    """Contract tests for Rule 5 (legacy behaviour) and Rule 6 (verifier phases)."""

    def setUp(self):
        self.logging_patch = patch.object(
            HermesSprintRunner, "_setup_logging", return_value=MagicMock()
        )
        self.logging_patch.start()
        self.addCleanup(self.logging_patch.stop)

    def make_phase_runner(
        self,
        root,
        role="builder",
        changed_files=None,
        owned_paths=None,
        include_role=True,
    ):
        phase = {
            "name": "phase-test",
            "agent": "codex",
            "worktree_dir": "worker",
            "branch": "s07/worker",
            "prompt_file": "prompts/s02-agy.md",
            "expected_handoff": "HANDOFF.md",
            "commit_message": "test: phase",
        }
        if include_role:
            phase["role"] = role
        if owned_paths is not None:
            phase["owned_paths"] = owned_paths

        spec_file = root / "spec.json"
        spec_content = {
            "sprint_id": "legacy-verifier-test",
            "control_root": str(runner_path.parent.parent),
            "target_repo": str(runner_path.parent.parent),
            "target_branch": "s07/integration",
            "worktree_root": str(root / "worktrees"),
            "runs_root": str(root / "runs"),
            "phases": [phase],
        }
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text(json.dumps(spec_content), encoding="utf-8")

        runner = HermesSprintRunner(
            spec_path=spec_file,
            skip_agent_exec=True,
        )
        runner.worktree_root = root / "worktrees"
        (runner.worktree_root / "worker").mkdir(parents=True, exist_ok=True)
        (runner.worktree_root / "integration").mkdir(parents=True, exist_ok=True)

        runner._prepare_handoff_path = MagicMock(
            return_value=(runner.worktree_root / "worker" / "HANDOFF.md", None)
        )
        runner._restore_handoff_path = MagicMock()
        runner.capture_handoff = MagicMock()
        runner.inspect_changed_files = MagicMock(
            return_value=changed_files if changed_files is not None else []
        )
        runner.validate_python_syntax = MagicMock()

        def command_result(command, **kwargs):
            stdout = "abc123\n" if command[:3] == ["git", "rev-parse", "HEAD"] else ""
            return subprocess.CompletedProcess(command, 0, stdout, "")

        runner.run_cmd = MagicMock(side_effect=command_result)
        return runner, phase

    # -------------------------------------------------------------------------
    # Rule 5: Unchanged Legacy Behaviour
    # -------------------------------------------------------------------------

    def test_builder_without_owned_paths_allows_changes_anywhere(self):
        """Rule 5: Builders without owned_paths can modify any path in the worktree."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                role="builder",
                changed_files=[
                    " M backend/api.py",
                    " M frontend/app.js",
                    " M README.md",
                ],
                owned_paths=None,
            )
            runner.execute_phase(phase)

            commands = [call.args[0] for call in runner.run_cmd.call_args_list]
            self.assertIn(["git", "add", "."], commands)
            self.assertTrue(any(cmd[:2] == ["git", "commit"] for cmd in commands))
            self.assertTrue(any(cmd[:2] == ["git", "merge"] for cmd in commands))
            self.assertTrue(runner.run_summary["phases"][0]["integrated"])

    def test_builder_without_owned_paths_requires_changes(self):
        """Rule 5: Builder without owned_paths still fails with FAILED_NO_CHANGES if clean."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                role="builder",
                changed_files=[],
                owned_paths=None,
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                runner.execute_phase(phase)
            self.assertEqual(ctx.exception.code, "FAILED_NO_CHANGES")

    def test_legacy_phase_without_owned_paths_commits_and_integrates(self):
        """Rule 5: Role-omitted legacy phase keeps current commit and integration behaviour."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                changed_files=[" M anywhere/file.py"],
                owned_paths=None,
                include_role=False,
            )
            runner.execute_phase(phase)

            self.assertEqual(runner.run_summary["phases"][0]["role"], "legacy")
            self.assertTrue(runner.run_summary["phases"][0]["integrated"])

    def test_hardener_without_owned_paths_integrates_only_when_changes_exist(self):
        """Rule 5: Hardener without owned_paths keeps conditional integration behaviour."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            # With changes
            changed_runner, changed_phase = self.make_phase_runner(
                root / "changed",
                role="hardener",
                changed_files=[" M any/product.py"],
                owned_paths=None,
            )
            changed_runner.execute_phase(changed_phase)
            self.assertTrue(changed_runner.run_summary["phases"][0]["integrated"])

            # Clean
            clean_runner, clean_phase = self.make_phase_runner(
                root / "clean",
                role="hardener",
                changed_files=[],
                owned_paths=None,
            )
            clean_runner.execute_phase(clean_phase)
            self.assertFalse(clean_runner.run_summary["phases"][0]["integrated"])

    # -------------------------------------------------------------------------
    # Rule 6: Verifier Phases Forbid Changes Regardless of Ownership
    # -------------------------------------------------------------------------

    def test_verifier_forbids_changes_even_inside_owned_paths(self):
        """Rule 6: Verifier phase modifies file inside owned_paths -> FAILED_FORBIDDEN_CHANGES."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                role="verifier",
                changed_files=[" M backend/api.py"],
                owned_paths=["backend/"],
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                runner.execute_phase(phase)

            self.assertEqual(ctx.exception.code, "FAILED_FORBIDDEN_CHANGES")
            commands = [call.args[0] for call in runner.run_cmd.call_args_list]
            self.assertFalse(any(cmd[:2] == ["git", "commit"] for cmd in commands))
            self.assertFalse(any(cmd[:2] == ["git", "merge"] for cmd in commands))

    def test_verifier_forbids_changes_outside_owned_paths(self):
        """Rule 6: Verifier phase modifies file outside owned_paths -> FAILED_FORBIDDEN_CHANGES."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                role="verifier",
                changed_files=[" M docs/readme.txt"],
                owned_paths=["backend/"],
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                runner.execute_phase(phase)

            self.assertEqual(ctx.exception.code, "FAILED_FORBIDDEN_CHANGES")

    def test_verifier_with_owned_paths_succeeds_when_clean(self):
        """Rule 6: Clean verifier with owned_paths succeeds and does not integrate."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                role="verifier",
                changed_files=[],
                owned_paths=["backend/"],
            )
            runner.execute_phase(phase)

            commands = [call.args[0] for call in runner.run_cmd.call_args_list]
            self.assertFalse(any(cmd[:2] == ["git", "commit"] for cmd in commands))
            self.assertFalse(any(cmd[:2] == ["git", "merge"] for cmd in commands))
            self.assertFalse(runner.run_summary["phases"][0]["integrated"])
            self.assertEqual(runner.run_summary["phases"][0]["status"], "SUCCESS")

    def test_verifier_without_owned_paths_still_forbids_changes(self):
        """Rule 6: Legacy verifier without owned_paths still forbids any target change."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(
                root,
                role="verifier",
                changed_files=[" M any/file.py"],
                owned_paths=None,
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                runner.execute_phase(phase)

            self.assertEqual(ctx.exception.code, "FAILED_FORBIDDEN_CHANGES")


class TestOwnershipHardening(unittest.TestCase):
    """S07b hardening: porcelain parsing, renames, load-time validation."""

    setUp = TestBuilderOwnershipEnforcement.setUp
    make_phase_runner = TestBuilderOwnershipEnforcement.make_phase_runner

    def test_real_unstaged_modification_inside_owned_paths_succeeds(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner, phase = self.make_phase_runner(root, owned_paths=["backend/"])
            repo = root / "repo"
            (repo / "backend").mkdir(parents=True)
            (repo / "backend" / "api.py").write_text("a = 1\n", encoding="utf-8")
            git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
            for command in (
                ["git", "init", "-q"],
                ["git", "add", "."],
                [*git, "commit", "-q", "-m", "init"],
            ):
                subprocess.run(command, cwd=repo, check=True, capture_output=True)
            (repo / "backend" / "api.py").write_text("a = 2\n", encoding="utf-8")

            runner.run_cmd = lambda *a, **k: HermesSprintRunner.run_cmd(runner, *a, **k)
            changed = HermesSprintRunner.inspect_changed_files(runner, repo)

            self.assertEqual(changed, [" M backend/api.py"])
            runner._enforce_phase_ownership(phase, changed)

    def test_rename_from_outside_owned_paths_into_owned_paths_fails(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            runner, phase = self.make_phase_runner(
                Path(temporary_dir),
                changed_files=["R  frontend/app.js -> backend/app.js"],
                owned_paths=["backend/"],
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                runner.execute_phase(phase)
            self.assertEqual(ctx.exception.code, "FAILED_OUTSIDE_OWNERSHIP")

    def _overlapping_spec(self, root):
        phases = [
            {
                "name": name,
                "role": "builder",
                "agent": "codex",
                "worktree_dir": name,
                "branch": f"s07/{name}",
                "prompt_file": "prompts/s02-agy.md",
                "expected_handoff": "HANDOFF.md",
                "commit_message": f"test: {name}",
                "owned_paths": paths,
                "parallel_group": "g",
            }
            for name, paths in (("a", ["backend/"]), ("b", ["backend/api/"]))
        ]
        return self._write_spec(root, phases)

    def _write_spec(self, root, phases):
        spec_file = root / "spec.json"
        spec_file.write_text(
            json.dumps(
                {
                    "sprint_id": "hardening",
                    "control_root": str(runner_path.parent.parent),
                    "target_repo": str(runner_path.parent.parent),
                    "worktree_root": str(root / "worktrees"),
                    "runs_root": str(root / "runs"),
                    "phases": phases,
                }
            ),
            encoding="utf-8",
        )
        return spec_file

    def test_overlap_rejected_at_load_time(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            spec_file = self._overlapping_spec(Path(temporary_dir))
            with self.assertRaises(SprintRunnerError) as ctx:
                HermesSprintRunner(spec_file, dry_run=True, skip_agent_exec=True)
            self.assertEqual(ctx.exception.code, "FAILED_INVALID_OWNERSHIP")

    def test_non_list_owned_paths_raise_validation_error_at_load(self):
        for bad_value in (123, True):
            with self.subTest(bad_value=bad_value):
                with tempfile.TemporaryDirectory() as temporary_dir:
                    root = Path(temporary_dir)
                    phase = {
                        "name": "p",
                        "role": "builder",
                        "agent": "codex",
                        "worktree_dir": "p",
                        "branch": "s07/p",
                        "prompt_file": "prompts/s02-agy.md",
                        "expected_handoff": "HANDOFF.md",
                        "commit_message": "test: p",
                        "owned_paths": bad_value,
                    }
                    spec_file = self._write_spec(root, [phase])
                    with self.assertRaises(SprintRunnerError) as ctx:
                        HermesSprintRunner(spec_file, dry_run=True, skip_agent_exec=True)
                    self.assertEqual(ctx.exception.code, "FAILED_INVALID_OWNERSHIP")

    def test_invalid_spec_does_no_worktree_setup(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            spec_file = self._overlapping_spec(root)
            with patch.object(HermesSprintRunner, "run_cmd") as run_cmd, patch.object(
                HermesSprintRunner, "prepare_environment"
            ) as prepare:
                with self.assertRaises(SprintRunnerError):
                    HermesSprintRunner(spec_file, skip_agent_exec=True)
            run_cmd.assert_not_called()
            prepare.assert_not_called()
            self.assertFalse((root / "worktrees").exists())


if __name__ == "__main__":
    unittest.main()
