import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from agents.errors import SprintRunnerError

from .base import ExecutionBackend, ExecutionResult


class HerdrBackend(ExecutionBackend):
    """Host one-shot worker CLIs in runner-owned persistent Herdr panes."""

    name = "herdr"

    def __init__(
        self,
        run_dir,
        sprint_id,
        logger=None,
        keep_workspace=True,
        run_process=None,
        which_func=None,
        herdr_executable="herdr",
        **kwargs,
    ):
        self.run_dir = Path(run_dir)
        self.sprint_id = sprint_id
        self.logger = logger
        self.keep_workspace = keep_workspace
        self._run_process = run_process or subprocess.run
        self._which = which_func or shutil.which
        self.herdr_executable = herdr_executable
        self.workspace_id = None
        self.root_pane_id = None
        self.created_pane_ids = []
        self.herdr_dir = self.run_dir / "herdr"
        self.wrapper_dir = self.run_dir / "wrappers"
        self.commands_log = self.herdr_dir / "commands.log"
        self.runtime_file = self.herdr_dir / "runtime.json"

    def execute(self, request):
        self.preflight(request.command[0])
        self._ensure_workspace(request.cwd)
        pane_id = self._create_worker_pane(request)
        wrapper_path, nonce, exit_file = self.build_wrapper(request)
        marker_regex = self.completion_regex(nonce)

        try:
            self._run_json(
                ["pane", "run", pane_id, f"bash {shlex.quote(str(wrapper_path))}"],
                failure_code="FAILED_HERDR_COMMAND",
                allow_empty_output=True,
            )
            try:
                self._run_json(
                    [
                        "pane",
                        "wait-output",
                        pane_id,
                        "--regex",
                        marker_regex,
                        "--source",
                        "recent-unwrapped",
                        "--lines",
                        "2000",
                        "--timeout",
                        str(request.timeout_seconds * 1000),
                    ],
                    failure_code="FAILED_HERDR_COMMAND",
                    process_timeout=request.timeout_seconds + 5,
                )
            except SprintRunnerError as exc:
                if exc.code == "FAILED_TIMEOUT" or "timeout" in exc.message.lower():
                    self._interrupt_pane(pane_id)
                    raise SprintRunnerError(
                        "FAILED_TIMEOUT",
                        f"Agent {request.agent_name} timed out after "
                        f"{request.timeout_seconds} seconds in Herdr pane {pane_id}",
                    ) from exc
                raise

            if not exit_file.exists():
                raise SprintRunnerError(
                    "FAILED_HERDR_PROTOCOL",
                    f"Herdr completion marker appeared without an exit status for pane {pane_id}",
                )
            try:
                returncode = int(exit_file.read_text(encoding="utf-8").strip())
            except (OSError, ValueError) as exc:
                raise SprintRunnerError(
                    "FAILED_HERDR_PROTOCOL",
                    f"Invalid worker exit status for Herdr pane {pane_id}",
                ) from exc
        finally:
            try:
                wrapper_path.unlink(missing_ok=True)
            except OSError:
                pass

        stdout = _read_text(request.stdout_file)
        stderr = _read_text(request.stderr_file)
        runtime_metadata = {
            "herdr_workspace_id": self.workspace_id,
            "herdr_pane_id": pane_id,
        }
        self._record_operation("worker_complete", pane_id=pane_id, status=returncode)
        return ExecutionResult(
            command=tuple(request.command),
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            backend=self.name,
            runtime_metadata=runtime_metadata,
        )

    def preflight(self, worker_executable):
        if self._which(self.herdr_executable) is None:
            raise SprintRunnerError(
                "FAILED_HERDR_EXECUTABLE_MISSING",
                f"Herdr executable was not found: {self.herdr_executable}",
            )
        if not _executable_exists(worker_executable, self._which):
            raise SprintRunnerError(
                "FAILED_AGENT_EXECUTABLE_MISSING",
                f"Worker executable was not found: {worker_executable}",
            )
        self._run_json(
            ["api", "snapshot"], failure_code="FAILED_HERDR_UNAVAILABLE"
        )

    def _ensure_workspace(self, cwd):
        if self.workspace_id is not None:
            return
        response = self._run_json(
            [
                "workspace",
                "create",
                "--cwd",
                str(cwd),
                "--label",
                f"Hermes Lab — {self.sprint_id}",
                "--no-focus",
            ],
            failure_code="FAILED_HERDR_COMMAND",
        )
        self.workspace_id = self._extract_id(
            response, ("result", "workspace", "workspace_id"), "workspace"
        )
        self.root_pane_id = self._extract_id(
            response, ("result", "root_pane", "pane_id"), "root pane"
        )
        self._record_operation("workspace_create", pane_id=self.root_pane_id)
        self._write_runtime()

    def _create_worker_pane(self, request):
        response = self._run_json(
            [
                "pane",
                "split",
                self.root_pane_id,
                "--direction",
                "down",
                "--cwd",
                str(request.cwd),
                "--no-focus",
            ],
            failure_code="FAILED_HERDR_COMMAND",
        )
        pane_id = self._extract_id(
            response, ("result", "pane", "pane_id"), "worker pane"
        )
        self.created_pane_ids.append(pane_id)
        label = str(request.metadata.get("phase", request.agent_name))[:80]
        self._run_json(
            ["pane", "rename", pane_id, label],
            failure_code="FAILED_HERDR_COMMAND",
        )
        self._record_operation("pane_create", pane_id=pane_id)
        self._write_runtime()
        return pane_id

    def build_wrapper(self, request):
        self.wrapper_dir.mkdir(parents=True, exist_ok=True)
        request.stdout_file.parent.mkdir(parents=True, exist_ok=True)
        nonce = secrets.token_hex(16)
        phase = _safe_name(str(request.metadata.get("phase", request.agent_name)))
        wrapper_path = self.wrapper_dir / f"{phase}_{nonce}.sh"
        exit_file = self.herdr_dir / f"{phase}_{nonce}.exit"
        self.herdr_dir.mkdir(parents=True, exist_ok=True)
        quoted_argv = "\n".join(f"  {shlex.quote(str(arg))}" for arg in request.command)
        marker = self.completion_marker(nonce)
        script = f"""#!/usr/bin/env bash
set +e
command=(
{quoted_argv}
)
: > {shlex.quote(str(request.stdout_file))}
: > {shlex.quote(str(request.stderr_file))}
"${{command[@]}}" > >(tee -a {shlex.quote(str(request.stdout_file))}) 2> >(tee -a {shlex.quote(str(request.stderr_file))} >&2)
status=$?
wait
printf '%s' "$status" > {shlex.quote(str(exit_file))}
printf '\\n%s:%s\\n' {shlex.quote(marker)} "$status"
exit 0
"""
        wrapper_path.write_text(script, encoding="utf-8")
        wrapper_path.chmod(0o700)
        return wrapper_path, nonce, exit_file

    @staticmethod
    def completion_marker(nonce):
        return f"__HERMES_LAB_COMPLETE_{nonce}__"

    @classmethod
    def completion_regex(cls, nonce):
        return rf"(?m)^{re.escape(cls.completion_marker(nonce))}:[0-9]+$"

    @classmethod
    def parse_completion(cls, text, nonce):
        pattern = re.compile(cls.completion_regex(nonce))
        match = pattern.search(text)
        if match is None:
            return None
        return int(match.group(0).rsplit(":", 1)[1])

    @staticmethod
    def _extract_id(payload, path, label):
        value = payload
        try:
            for key in path:
                value = value[key]
        except (KeyError, TypeError) as exc:
            raise SprintRunnerError(
                "FAILED_HERDR_PROTOCOL", f"Herdr response omitted {label} ID"
            ) from exc
        if not isinstance(value, str) or not value:
            raise SprintRunnerError(
                "FAILED_HERDR_PROTOCOL", f"Herdr returned an invalid {label} ID"
            )
        return value

    def _run_json(
        self, args, failure_code, process_timeout=30, allow_empty_output=False
    ):
        command = [self.herdr_executable, *args]
        self._record_operation("herdr_call", target=args[0] if args else None)
        try:
            result = self._run_process(
                command,
                capture_output=True,
                text=True,
                timeout=process_timeout,
            )
        except FileNotFoundError as exc:
            raise SprintRunnerError(
                "FAILED_HERDR_EXECUTABLE_MISSING",
                f"Herdr executable was not found: {self.herdr_executable}",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SprintRunnerError(
                "FAILED_TIMEOUT", f"Herdr command timed out: {args[0]}"
            ) from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown Herdr error").strip()
            raise SprintRunnerError(failure_code, f"Herdr command failed: {detail}")
        if allow_empty_output and not result.stdout.strip():
            return {}
        try:
            payload = json.loads(result.stdout)
        except (TypeError, json.JSONDecodeError) as exc:
            raise SprintRunnerError(
                "FAILED_HERDR_PROTOCOL",
                f"Herdr returned malformed JSON for {args[0]}",
            ) from exc
        if not isinstance(payload, dict):
            raise SprintRunnerError(
                "FAILED_HERDR_PROTOCOL", "Herdr JSON response was not an object"
            )
        return payload

    def _interrupt_pane(self, pane_id):
        try:
            self._run_json(
                ["pane", "send-keys", pane_id, "ctrl+c"],
                failure_code="FAILED_HERDR_COMMAND",
            )
        except SprintRunnerError:
            pass
        self._record_operation("pane_interrupt", pane_id=pane_id)

    def cleanup(self, success=False):
        if self.keep_workspace or self.workspace_id is None:
            return
        owned_workspace = self.workspace_id
        self._run_json(
            ["workspace", "close", owned_workspace],
            failure_code="FAILED_HERDR_COMMAND",
        )
        self._record_operation("workspace_close", workspace_id=owned_workspace)
        self.workspace_id = None
        self.root_pane_id = None
        self.created_pane_ids.clear()
        self._write_runtime()

    def _record_operation(self, operation, **details):
        self.herdr_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            **details,
        }
        with self.commands_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _write_runtime(self):
        self.herdr_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "workspace_id": self.workspace_id,
            "root_pane_id": self.root_pane_id,
            "worker_pane_ids": list(self.created_pane_ids),
            "keep_workspace": self.keep_workspace,
        }
        self.runtime_file.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def _read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _executable_exists(executable, which_func):
    if os.sep in str(executable):
        return os.access(executable, os.X_OK)
    return which_func(executable) is not None


def _safe_name(value):
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_")
    return cleaned or "worker"
