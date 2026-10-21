import importlib.util
import inspect
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


RUNNER_PATH = Path(__file__).resolve().parent.parent / "runner" / "run-hermes-sprint.py"
SPEC = importlib.util.spec_from_file_location("run_hermes_sprint_backends", RUNNER_PATH)
RUNNER_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER_MODULE)

HermesSprintRunner = RUNNER_MODULE.HermesSprintRunner
SprintRunnerError = RUNNER_MODULE.SprintRunnerError

from backends.base import ExecutionRequest
from backends.herdr_backend import HerdrBackend, Seat, SeatPool
from backends.registry import BackendRegistry, default_backend_registry
from backends.subprocess_backend import SubprocessBackend


def completed(command=None, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(command or [], returncode, stdout, stderr)


class BackendTestCase(unittest.TestCase):
    def make_request(self, root, command=None, timeout=5):
        root = Path(root)
        return ExecutionRequest(
            agent_name="test-worker",
            command=tuple(command or [sys.executable, "-c", "print('ok')"]),
            cwd=root,
            timeout_seconds=timeout,
            stdout_file=root / "stdout.log",
            stderr_file=root / "stderr.log",
            metadata={"phase": "backend_test"},
        )


class TestBackendRegistryAndSelection(BackendTestCase):
    def setUp(self):
        self.logging_patch = patch.object(
            HermesSprintRunner, "_setup_logging", return_value=MagicMock()
        )
        self.logging_patch.start()
        self.addCleanup(self.logging_patch.stop)

    def test_known_and_unknown_backends(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            kwargs = {"run_dir": temporary_dir, "sprint_id": "test"}
            self.assertIsInstance(
                default_backend_registry.get("subprocess", **kwargs), SubprocessBackend
            )
            self.assertIsInstance(
                default_backend_registry.get("herdr", **kwargs), HerdrBackend
            )
        unsupported = MagicMock()
        registry = BackendRegistry({"known": unsupported})
        with self.assertRaises(SprintRunnerError) as ctx:
            registry.get("missing")
        self.assertEqual(ctx.exception.code, "FAILED_UNKNOWN_BACKEND")
        unsupported.assert_not_called()

    def test_backend_selection_precedence(self):
        runner = HermesSprintRunner(
            spec_path=Path(__file__).resolve().parent.parent / "sprints" / "lab-s03.json",
            dry_run=True,
            skip_agent_exec=True,
            backend_override="herdr",
        )
        self.assertEqual(runner.resolve_backend_name({}), "herdr")
        self.assertEqual(
            runner.resolve_backend_name({"execution_backend": "subprocess"}),
            "subprocess",
        )
        runner.backend_override = None
        runner.spec["execution_backend"] = "herdr"
        self.assertEqual(runner.resolve_backend_name({}), "herdr")
        runner.spec.pop("execution_backend")
        self.assertEqual(runner.resolve_backend_name({}), "subprocess")

    def test_backends_do_not_own_git_promotion(self):
        source = inspect.getsource(SubprocessBackend) + inspect.getsource(HerdrBackend)
        for operation in ("git add", "git commit", "git merge", "git rebase", "git push"):
            self.assertNotIn(operation, source)


class TestSprintEndReleasesPooledJob(BackendTestCase):
    def setUp(self):
        self.logging_patch = patch.object(
            HermesSprintRunner, "_setup_logging", return_value=MagicMock()
        )
        self.logging_patch.start()
        self.addCleanup(self.logging_patch.stop)

    def make_failing_runner(self, temporary_dir):
        runner = HermesSprintRunner(
            spec_path=Path(__file__).resolve().parent.parent / "sprints" / "lab-s03.json",
            dry_run=True,
            skip_agent_exec=True,
        )
        runner.summary_file = Path(temporary_dir) / "summary.json"
        return runner

    def run_failing_sprint(self, runner):
        # Fail the sprint early so execute() reaches its finally block.
        with patch.object(runner, "preflight", side_effect=SprintRunnerError("FAILED_TEST", "boom")):
            try:
                runner.execute()
            except SprintRunnerError:
                pass

    def test_sprint_end_releases_the_sprints_pooled_seats(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            runner = self.make_failing_runner(temporary_dir)
            backend = MagicMock()
            runner._backend_cache = {"openrig": backend}

            self.run_failing_sprint(runner)

            backend.cleanup.assert_called_once()
            backend.release_job.assert_called_once_with(runner.sprint_id)

    def test_a_failed_job_release_is_logged_and_the_run_summary_still_written(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            runner = self.make_failing_runner(temporary_dir)
            backend = MagicMock()
            backend.release_job.side_effect = SprintRunnerError("FAILED_OPENRIG_UNAVAILABLE", "daemon down")
            runner._backend_cache = {"openrig": backend}

            self.run_failing_sprint(runner)

            self.assertTrue(runner.summary_file.exists())
            runner.logger.error.assert_any_call(
                "Backend job release failed: [%s] %s", "FAILED_OPENRIG_UNAVAILABLE", "daemon down"
            )


class TestSubprocessBackend(BackendTestCase):
    def test_success_captures_stdout_stderr_and_exit(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            request = self.make_request(temporary_dir)
            backend = SubprocessBackend()
            result = backend.execute(request)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "ok\n")
            self.assertEqual(result.stderr, "")
            self.assertEqual(result.backend, "subprocess")
            self.assertEqual(request.stdout_file.read_text(encoding="utf-8"), "ok\n")

    def test_nonzero_exit_is_returned_for_adapter_handling(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            request = self.make_request(temporary_dir)
            backend = SubprocessBackend(
                run_process=MagicMock(return_value=completed(returncode=9, stderr="denied"))
            )
            result = backend.execute(request)
            self.assertEqual(result.returncode, 9)
            self.assertEqual(result.stderr, "denied")

    def test_timeout_preserves_partial_output(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            request = self.make_request(temporary_dir)
            timeout = subprocess.TimeoutExpired(
                request.command, request.timeout_seconds, output=b"partial", stderr=b"warning"
            )
            backend = SubprocessBackend(run_process=MagicMock(side_effect=timeout))
            with self.assertRaises(SprintRunnerError) as ctx:
                backend.execute(request)
            self.assertEqual(ctx.exception.code, "FAILED_TIMEOUT")
            self.assertEqual(request.stdout_file.read_text(encoding="utf-8"), "partial")
            self.assertEqual(request.stderr_file.read_text(encoding="utf-8"), "warning")

    def test_missing_executable_is_clear(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            request = self.make_request(temporary_dir, command=["missing-worker"])
            backend = SubprocessBackend(run_process=MagicMock(side_effect=FileNotFoundError()))
            with self.assertRaises(SprintRunnerError) as ctx:
                backend.execute(request)
            self.assertEqual(ctx.exception.code, "FAILED_AGENT_EXECUTABLE_MISSING")


class TestHerdrBackend(BackendTestCase):
    def make_backend(self, root, responses=None, which=None, keep=True):
        return HerdrBackend(
            run_dir=root,
            sprint_id="lab-test",
            keep_workspace=keep,
            run_process=MagicMock(side_effect=responses) if responses is not None else MagicMock(),
            which_func=which or (lambda executable: f"/usr/bin/{executable}"),
        )

    def test_preflight_missing_herdr(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            backend = self.make_backend(temporary_dir, which=lambda executable: None)
            with self.assertRaises(SprintRunnerError) as ctx:
                backend.preflight("worker")
            self.assertEqual(ctx.exception.code, "FAILED_HERDR_EXECUTABLE_MISSING")

    def test_preflight_missing_worker(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            backend = self.make_backend(
                temporary_dir,
                which=lambda executable: "/usr/bin/herdr" if executable == "herdr" else None,
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                backend.preflight("worker")
            self.assertEqual(ctx.exception.code, "FAILED_AGENT_EXECUTABLE_MISSING")

    def test_preflight_server_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            backend = self.make_backend(
                temporary_dir,
                responses=[completed(returncode=1, stderr='{"error":"offline"}')],
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                backend.preflight("worker")
            self.assertEqual(ctx.exception.code, "FAILED_HERDR_UNAVAILABLE")
            command = backend._run_process.call_args.args[0]
            self.assertEqual(command, ["herdr", "api", "snapshot"])

    def test_malformed_json_is_protocol_failure(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            backend = self.make_backend(
                temporary_dir, responses=[completed(stdout="not-json")]
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                backend.preflight("worker")
            self.assertEqual(ctx.exception.code, "FAILED_HERDR_PROTOCOL")

    def test_workspace_and_pane_ids_are_parsed_from_json(self):
        workspace = {
            "result": {
                "workspace": {"workspace_id": "opaque-workspace"},
                "root_pane": {"pane_id": "opaque-root"},
            }
        }
        pane = {"result": {"pane": {"pane_id": "opaque-worker"}}}
        with tempfile.TemporaryDirectory() as temporary_dir:
            backend = self.make_backend(
                temporary_dir,
                responses=[
                    completed(stdout=json.dumps(workspace)),
                    completed(stdout=json.dumps(pane)),
                    completed(stdout="{}"),
                ],
            )
            backend._ensure_workspace(Path(temporary_dir))
            request = self.make_request(temporary_dir)
            pane_id = backend._create_worker_pane(request)
            self.assertEqual(backend.workspace_id, "opaque-workspace")
            self.assertEqual(backend.root_pane_id, "opaque-root")
            self.assertEqual(pane_id, "opaque-worker")

    def test_missing_json_id_is_protocol_failure(self):
        with self.assertRaises(SprintRunnerError) as ctx:
            HerdrBackend._extract_id({"result": {}}, ("result", "pane", "pane_id"), "pane")
        self.assertEqual(ctx.exception.code, "FAILED_HERDR_PROTOCOL")

    def test_failed_workspace_and_pane_commands_are_distinct(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            backend = self.make_backend(
                temporary_dir, responses=[completed(returncode=1, stderr="create failed")]
            )
            with self.assertRaises(SprintRunnerError) as workspace_ctx:
                backend._ensure_workspace(Path(temporary_dir))
            self.assertEqual(workspace_ctx.exception.code, "FAILED_HERDR_COMMAND")

        workspace = {
            "result": {
                "workspace": {"workspace_id": "w"},
                "root_pane": {"pane_id": "root"},
            }
        }
        with tempfile.TemporaryDirectory() as temporary_dir:
            backend = self.make_backend(
                temporary_dir,
                responses=[
                    completed(stdout=json.dumps(workspace)),
                    completed(returncode=1, stderr="split failed"),
                ],
            )
            backend._ensure_workspace(Path(temporary_dir))
            with self.assertRaises(SprintRunnerError) as pane_ctx:
                backend._create_worker_pane(self.make_request(temporary_dir))
            self.assertEqual(pane_ctx.exception.code, "FAILED_HERDR_COMMAND")

    @unittest.skipIf(
        os.name == "nt",
        "Herdr worker wrappers are Bash/POSIX-only on native Windows",
    )
    def test_execute_round_trip_uses_returned_ids_and_captures_result(self):
        workspace = {
            "result": {
                "workspace": {"workspace_id": "runtime-workspace"},
                "root_pane": {"pane_id": "runtime-root"},
            }
        }
        pane = {"result": {"pane": {"pane_id": "runtime-worker"}}}

        def fake_herdr(command, **kwargs):
            if command[1:3] == ["api", "snapshot"]:
                return completed(command, stdout="{}")
            if command[1:3] == ["workspace", "create"]:
                return completed(command, stdout=json.dumps(workspace))
            if command[1:3] == ["pane", "split"]:
                return completed(command, stdout=json.dumps(pane))
            if command[1:3] == ["pane", "rename"]:
                return completed(command, stdout="{}")
            if command[1:3] == ["pane", "run"]:
                wrapper_result = subprocess.run(
                    shlex.split(command[-1]), capture_output=True, text=True, timeout=5
                )
                self.assertEqual(wrapper_result.returncode, 0, wrapper_result.stderr)
                return completed(command, stdout="")
            if command[1:3] == ["pane", "wait-output"]:
                return completed(command, stdout="{}")
            self.fail(f"Unexpected Herdr command: {command}")

        with tempfile.TemporaryDirectory() as temporary_dir:
            request = self.make_request(
                temporary_dir,
                command=[sys.executable, "-c", "import sys; print('hosted'); print('warn', file=sys.stderr)"],
            )
            backend = HerdrBackend(
                run_dir=temporary_dir,
                sprint_id="lab-test",
                run_process=fake_herdr,
                which_func=lambda executable: f"/usr/bin/{executable}",
            )
            result = backend.execute(request)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "hosted\n")
            self.assertEqual(result.stderr, "warn\n")
            self.assertEqual(result.backend, "herdr")
            self.assertEqual(
                result.runtime_metadata,
                {
                    "herdr_workspace_id": "runtime-workspace",
                    "herdr_pane_id": "runtime-worker",
                },
            )
            command_log = backend.commands_log.read_text(encoding="utf-8")
            self.assertNotIn("import sys", command_log)
            self.assertNotIn("hosted", command_log)

    def test_failed_pane_run_maps_to_herdr_command(self):
        workspace = {
            "result": {
                "workspace": {"workspace_id": "w"},
                "root_pane": {"pane_id": "root"},
            }
        }
        pane = {"result": {"pane": {"pane_id": "worker"}}}
        responses = [
            completed(stdout="{}"),
            completed(stdout=json.dumps(workspace)),
            completed(stdout=json.dumps(pane)),
            completed(stdout="{}"),
            completed(returncode=1, stderr="pane run failed"),
        ]
        with tempfile.TemporaryDirectory() as temporary_dir:
            backend = self.make_backend(temporary_dir, responses=responses)
            with self.assertRaises(SprintRunnerError) as ctx:
                backend.execute(self.make_request(temporary_dir))
            self.assertEqual(ctx.exception.code, "FAILED_HERDR_COMMAND")

    def test_wait_timeout_interrupts_only_worker_and_preserves_partial_logs(self):
        workspace = {
            "result": {
                "workspace": {"workspace_id": "w"},
                "root_pane": {"pane_id": "root"},
            }
        }
        pane = {"result": {"pane": {"pane_id": "worker"}}}

        def fake_herdr(command, **kwargs):
            if command[1:3] == ["api", "snapshot"]:
                return completed(command, stdout="{}")
            if command[1:3] == ["workspace", "create"]:
                return completed(command, stdout=json.dumps(workspace))
            if command[1:3] == ["pane", "split"]:
                return completed(command, stdout=json.dumps(pane))
            if command[1:3] in (["pane", "rename"], ["pane", "run"]):
                return completed(command, stdout="{}")
            if command[1:3] == ["pane", "wait-output"]:
                raise subprocess.TimeoutExpired(command, kwargs.get("timeout"))
            if command[1:3] == ["pane", "send-keys"]:
                return completed(command, stdout="{}")
            self.fail(f"Unexpected Herdr command: {command}")

        with tempfile.TemporaryDirectory() as temporary_dir:
            request = self.make_request(temporary_dir, timeout=1)
            request.stdout_file.write_text("partial output", encoding="utf-8")
            backend = HerdrBackend(
                run_dir=temporary_dir,
                sprint_id="lab-test",
                run_process=fake_herdr,
                which_func=lambda executable: f"/usr/bin/{executable}",
            )
            with self.assertRaises(SprintRunnerError) as ctx:
                backend.execute(request)
            self.assertEqual(ctx.exception.code, "FAILED_TIMEOUT")
            self.assertEqual(request.stdout_file.read_text(encoding="utf-8"), "partial output")
            calls = backend.commands_log.read_text(encoding="utf-8")
            self.assertIn("pane_interrupt", calls)
            self.assertNotIn("workspace_close", calls)

    @unittest.skipIf(
        os.name == "nt",
        "Herdr worker wrappers are Bash/POSIX-only on native Windows",
    )
    def test_wrapper_preserves_adversarial_arguments_without_injection(self):
        payloads = [
            "simple prompt",
            "line one\nline two",
            "single ' quote",
            'double " quote',
            "; semicolon",
            "&& conjunction",
            "| pipeline",
            "$(touch should-not-run)",
            "`touch should-not-run`",
            "Tiếng Việt — thử nghiệm",
            "# Markdown\n```python\nprint('large')\n```\n" * 100,
        ]
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            marker = root / "injected"
            payloads.append(f"; touch {marker}")
            code = "import json,sys; print(json.dumps(sys.argv[1:], ensure_ascii=False))"
            request = self.make_request(
                root, command=[sys.executable, "-c", code, *payloads]
            )
            backend = self.make_backend(root)
            wrapper, nonce, exit_file = backend.build_wrapper(request)
            process = subprocess.run(
                ["bash", str(wrapper)],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(json.loads(request.stdout_file.read_text(encoding="utf-8")), payloads)
            self.assertEqual(exit_file.read_text(encoding="utf-8"), "0")
            self.assertIn(HerdrBackend.completion_marker(nonce), process.stdout)
            self.assertFalse(marker.exists())

    def test_completion_sentinel_requires_exact_nonce_and_line(self):
        nonce = "abc123"
        marker = HerdrBackend.completion_marker(nonce)
        self.assertEqual(HerdrBackend.parse_completion(f"before\n{marker}:7\nafter", nonce), 7)
        self.assertIsNone(HerdrBackend.parse_completion(f"{marker}_similar:0", nonce))
        self.assertIsNone(HerdrBackend.parse_completion(f"{marker}:0", "wrong"))

    def test_cleanup_closes_only_owned_workspace(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            backend = self.make_backend(
                temporary_dir,
                responses=[completed(stdout="{}")],
                keep=False,
            )
            backend.workspace_id = "owned-workspace"
            backend.root_pane_id = "owned-root"
            backend.cleanup(success=True)
            command = backend._run_process.call_args.args[0]
            self.assertEqual(command, ["herdr", "workspace", "close", "owned-workspace"])
            self.assertNotIn("unrelated-workspace", command)


class FakeHerdrForSeatPool:
    def __init__(self, workspace_id="ws-pool", root_pane_id="root-pool"):
        self.workspace_id = workspace_id
        self.root_pane_id = root_pane_id
        self._lock = threading.Lock()
        self.pane_counter = 0
        self.panes = {}
        self.commands_run = []
        self.banners_seen = []
        self.interrupts = []
        self.slow_delay = 0.0

    def __call__(self, command, **kwargs):
        with self._lock:
            self.commands_run.append(list(command))
            sub = command[1:3]
            if sub == ["api", "snapshot"]:
                return completed(command, stdout="{}")
            if sub == ["workspace", "create"]:
                return completed(
                    command,
                    stdout=json.dumps({
                        "result": {
                            "workspace": {"workspace_id": self.workspace_id},
                            "root_pane": {"pane_id": self.root_pane_id},
                        }
                    }),
                )
            if sub == ["pane", "split"]:
                self.pane_counter += 1
                pid = f"pane-{self.pane_counter}"
                self.panes[pid] = None
                return completed(
                    command,
                    stdout=json.dumps({"result": {"pane": {"pane_id": pid}}}),
                )
            if sub == ["pane", "rename"]:
                pid = command[3]
                label = command[4]
                self.panes[pid] = label
                return completed(command, stdout="{}")
            if sub == ["pane", "run"]:
                wrapper_cmd = command[-1]
                run_res = subprocess.run(
                    shlex.split(wrapper_cmd),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if run_res.stdout:
                    for line in run_res.stdout.splitlines():
                        if line.startswith("=== [seat:"):
                            self.banners_seen.append(line)
                return completed(command, stdout="")
            if sub == ["pane", "wait-output"]:
                if self.slow_delay > 0:
                    time.sleep(self.slow_delay)
                return completed(command, stdout="{}")
            if sub == ["pane", "send-keys"]:
                pid = command[3]
                self.interrupts.append(pid)
                return completed(command, stdout="{}")
            if sub == ["workspace", "close"]:
                return completed(command, stdout="{}")
            raise AssertionError(f"Unexpected Herdr command: {command}")


@unittest.skipIf(sys.platform == 'win32', 'Herdr panes run a POSIX bash wrapper')
class TestHerdrSeatPool(BackendTestCase):
    def setUp(self):
        super().setUp()
        SeatPool.reset()

    def tearDown(self):
        SeatPool.reset()
        super().tearDown()

    def test_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            fake = FakeHerdrForSeatPool()
            events_seen = []
            backend = HerdrBackend(
                run_dir=temporary_dir,
                sprint_id="lab-test",
                run_process=fake,
                which_func=lambda ex: f"/usr/bin/{ex}",
                event_sink=events_seen.append,
            )
            self.assertIsNone(backend.seat_pool)
            req = self.make_request(temporary_dir)
            res = backend.execute(req)
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("herdr_seat", res.runtime_metadata)
            self.assertEqual(fake.banners_seen, [])
            acquired_events = [e for e in events_seen if e.kind == "execution.resource_acquired"]
            self.assertEqual(len(acquired_events), 1)
            self.assertEqual(acquired_events[0].metadata["resource"]["kind"], "pane")

    def test_two_concurrent_phases_get_different_seats(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            fake = FakeHerdrForSeatPool()
            backend = HerdrBackend(
                run_dir=temporary_dir,
                sprint_id="lab-test",
                run_process=fake,
                which_func=lambda ex: f"/usr/bin/{ex}",
                seat_pool={"size": 2, "hot": False},
            )

            results = []
            errors = []

            def worker(phase_name):
                try:
                    req = self.make_request(
                        temporary_dir,
                        command=[sys.executable, "-c", "import time; time.sleep(0.05); print('ok')"],
                    )
                    req.metadata["phase"] = phase_name
                    res = backend.execute(req)
                    results.append(res)
                except Exception as exc:
                    errors.append(exc)

            t1 = threading.Thread(target=worker, args=("phase-1",))
            t2 = threading.Thread(target=worker, args=("phase-2",))
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            self.assertEqual(errors, [])
            self.assertEqual(len(results), 2)
            seats = {r.runtime_metadata.get("herdr_seat") for r in results}
            self.assertEqual(seats, {"seat-1", "seat-2"})

    def test_third_phase_waits_and_gets_released_seat(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            fake = FakeHerdrForSeatPool()
            backend = HerdrBackend(
                run_dir=temporary_dir,
                sprint_id="lab-test",
                run_process=fake,
                which_func=lambda ex: f"/usr/bin/{ex}",
                seat_pool={"size": 2, "hot": False, "acquire_timeout_seconds": 5},
            )

            order = []
            errors = []

            def worker_slow(phase_name):
                try:
                    req = self.make_request(
                        temporary_dir,
                        command=[sys.executable, "-c", "import time; time.sleep(0.15); print('slow')"],
                    )
                    req.metadata["phase"] = phase_name
                    res = backend.execute(req)
                    order.append((phase_name, res.runtime_metadata.get("herdr_seat")))
                except Exception as exc:
                    errors.append(exc)

            def worker_waiter(phase_name):
                try:
                    time.sleep(0.05)
                    req = self.make_request(
                        temporary_dir,
                        command=[sys.executable, "-c", "print('fast')"],
                    )
                    req.metadata["phase"] = phase_name
                    res = backend.execute(req)
                    order.append((phase_name, res.runtime_metadata.get("herdr_seat")))
                except Exception as exc:
                    errors.append(exc)

            t1 = threading.Thread(target=worker_slow, args=("slow-1",))
            t2 = threading.Thread(target=worker_slow, args=("slow-2",))
            t3 = threading.Thread(target=worker_waiter, args=("waiter-3",))

            t1.start()
            t2.start()
            t3.start()
            t1.join()
            t2.join()
            t3.join()

            self.assertEqual(errors, [])
            self.assertEqual(len(order), 3)
            waiter_record = [item for item in order if item[0] == "waiter-3"][0]
            self.assertIn(waiter_record[1], {"seat-1", "seat-2"})

    def test_acquire_timeout(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            fake = FakeHerdrForSeatPool()
            backend = HerdrBackend(
                run_dir=temporary_dir,
                sprint_id="lab-test",
                run_process=fake,
                which_func=lambda ex: f"/usr/bin/{ex}",
                seat_pool={"size": 1, "hot": False, "acquire_timeout_seconds": 0.2},
            )

            started = threading.Event()
            finish = threading.Event()

            def holder():
                seat = backend.seat_pool.acquire(
                    is_hot=False, timeout=2.0, cwd=Path(temporary_dir), backend=backend
                )
                started.set()
                finish.wait()
                backend.seat_pool.release(seat)

            t = threading.Thread(target=holder)
            t.start()
            started.wait()

            try:
                req = self.make_request(temporary_dir)
                with self.assertRaises(SprintRunnerError) as ctx:
                    backend.execute(req)
                self.assertEqual(ctx.exception.code, "FAILED_SEAT_TIMEOUT")
                self.assertIn("Timed out waiting for a free Herdr seat", str(ctx.exception))
            finally:
                finish.set()
                t.join()

    def test_hot_seat_only_for_hot_phases_and_available_when_pool_full(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            fake = FakeHerdrForSeatPool()
            backend = HerdrBackend(
                run_dir=temporary_dir,
                sprint_id="lab-test",
                run_process=fake,
                which_func=lambda ex: f"/usr/bin/{ex}",
                seat_pool={"size": 1, "hot": True, "acquire_timeout_seconds": 0.2},
            )

            seat1 = backend.seat_pool.acquire(is_hot=False, cwd=Path(temporary_dir), backend=backend)
            self.assertEqual(seat1.label, "seat-1")

            try:
                normal_req = self.make_request(temporary_dir)
                with self.assertRaises(SprintRunnerError) as ctx:
                    backend.execute(normal_req)
                self.assertEqual(ctx.exception.code, "FAILED_SEAT_TIMEOUT")

                hot_req = self.make_request(temporary_dir)
                hot_req.metadata["priority"] = "hot"
                hot_res = backend.execute(hot_req)
                self.assertEqual(hot_res.runtime_metadata.get("herdr_seat"), "hot")
            finally:
                backend.seat_pool.release(seat1)

    def test_release_on_failure_and_cancel(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            fake = FakeHerdrForSeatPool()
            backend = HerdrBackend(
                run_dir=temporary_dir,
                sprint_id="lab-test",
                run_process=fake,
                which_func=lambda ex: f"/usr/bin/{ex}",
                seat_pool={"size": 1, "hot": False, "acquire_timeout_seconds": 1.0},
            )

            # 1. Non-zero exit code (failure)
            fail_req = self.make_request(
                temporary_dir,
                command=[sys.executable, "-c", "import sys; sys.exit(7)"],
            )
            res = backend.execute(fail_req)
            self.assertEqual(res.returncode, 7)
            # Seat is released, next execute succeeds
            ok_req = self.make_request(temporary_dir)
            ok_res = backend.execute(ok_req)
            self.assertEqual(ok_res.returncode, 0)

            # 2. Command exception
            with patch.object(backend, "_run_in_pane", side_effect=SprintRunnerError("FAILED_HERDR_COMMAND", "error")):
                with self.assertRaises(SprintRunnerError):
                    backend.execute(fail_req)
            # Seat is released, next execute succeeds
            ok_res2 = backend.execute(ok_req)
            self.assertEqual(ok_res2.returncode, 0)

            # 3. Cancel
            cancel_backend = HerdrBackend(
                run_dir=temporary_dir,
                sprint_id="lab-test",
                run_process=fake,
                which_func=lambda ex: f"/usr/bin/{ex}",
                seat_pool={"size": 1, "hot": False, "acquire_timeout_seconds": 1.0},
            )
            cancel_backend.cancel_event.set()
            with self.assertRaises(SprintRunnerError) as ctx:
                cancel_backend.execute(ok_req)
            self.assertEqual(ctx.exception.code, "FAILED_CANCELLED")
            # Seat is released, next execute with uncancelled backend succeeds
            ok_res3 = backend.execute(ok_req)
            self.assertEqual(ok_res3.returncode, 0)

    def test_banner_written(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            fake = FakeHerdrForSeatPool()
            backend = HerdrBackend(
                run_dir=temporary_dir,
                sprint_id="sprint-123",
                run_process=fake,
                which_func=lambda ex: f"/usr/bin/{ex}",
                seat_pool={"size": 2, "hot": True},
            )

            req = self.make_request(temporary_dir)
            req.metadata["phase"] = "scaffold"
            req.metadata["persona"] = "Hermes"
            backend.execute(req)

            expected_banner = "=== [seat:seat-1] job:sprint-123 phase:scaffold agent:Hermes ==="
            self.assertIn(expected_banner, fake.banners_seen)

            log_text = backend.commands_log.read_text(encoding="utf-8")
            self.assertIn("seat_banner", log_text)
            self.assertIn(expected_banner, log_text)

    def test_state_survives_across_backend_instances(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            fake = FakeHerdrForSeatPool()
            backend1 = HerdrBackend(
                run_dir=temporary_dir,
                sprint_id="shared-sprint",
                run_process=fake,
                which_func=lambda ex: f"/usr/bin/{ex}",
                seat_pool={"size": 2, "hot": True},
            )
            req1 = self.make_request(temporary_dir)
            res1 = backend1.execute(req1)
            self.assertEqual(res1.runtime_metadata["herdr_seat"], "seat-1")
            self.assertEqual(res1.runtime_metadata["herdr_pane_id"], "pane-1")
            self.assertEqual(fake.pane_counter, 1)

            # Clear in-memory pool to simulate fresh process
            SeatPool.clear_pool(temporary_dir, "shared-sprint")

            backend2 = HerdrBackend(
                run_dir=temporary_dir,
                sprint_id="shared-sprint",
                run_process=fake,
                which_func=lambda ex: f"/usr/bin/{ex}",
                seat_pool={"size": 2, "hot": True},
            )
            req2 = self.make_request(temporary_dir)
            res2 = backend2.execute(req2)
            self.assertEqual(res2.runtime_metadata["herdr_seat"], "seat-1")
            self.assertEqual(res2.runtime_metadata["herdr_pane_id"], "pane-1")
            # Did not split a new pane!
            self.assertEqual(fake.pane_counter, 1)


@unittest.skipUnless(
    os.name != "nt"
    and os.environ.get("HERDR_ENV") == "1"
    and shutil.which("herdr"),
    "Herdr smoke test requires a managed Herdr pane",
)
class TestHerdrSmoke(BackendTestCase):
    def test_harmless_shell_command(self):
        status = subprocess.run(
            ["herdr", "api", "snapshot"], capture_output=True, text=True, timeout=5
        )
        if status.returncode != 0:
            self.skipTest("Herdr server is unavailable")
        with tempfile.TemporaryDirectory() as temporary_dir:
            request = self.make_request(
                temporary_dir, command=["bash", "-c", "printf herdr-smoke"]
            )
            backend = HerdrBackend(
                run_dir=temporary_dir,
                sprint_id="herdr-smoke",
                keep_workspace=False,
            )
            try:
                result = backend.execute(request)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "herdr-smoke")
            finally:
                backend.cleanup(success=True)


if __name__ == "__main__":
    unittest.main()
