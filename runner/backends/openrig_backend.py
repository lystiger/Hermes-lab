import json
import re
import secrets
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from agents.errors import SprintRunnerError

from .base import ExecutionBackend, ExecutionResult


SUPPORTED_VERSION_PREFIX = "0.6."
# Hermes agent -> OpenRig runtime. Only runtimes whose hook rung OpenRig marks
# "standing" (exactly-once turn boundaries) can prove completion.
SUPPORTED_RUNTIMES = {"claude": "claude-code"}
WORKER_LOGICAL_ID = "hermes.worker"
RELEASE_TIMEOUT_SECONDS = 60
# Shared budget for finding a rig whose `rig up` response was lost (all retries together).
ORPHAN_RECOVERY_SECONDS = 20
ORPHAN_RECOVERY_ATTEMPTS = 3
SEND_IDLE_WAIT_SECONDS = 30


class OpenRigBackend(ExecutionBackend):
    """Run one task in an ephemeral, Hermes-owned single-seat OpenRig rig.

    OpenRig owns the seat lifecycle; Hermes owns everything else. Each execute()
    launches its own rig, proves completion from runtime-hook evidence plus a
    nonce-bound result file, and tears the rig down by its exact rigId.
    """

    name = "openrig"

    def __init__(
        self,
        run_dir,
        sprint_id,
        logger=None,
        run_process=None,
        which_func=None,
        rig_executable="rig",
        poll_interval=2.0,
        monotonic=None,
        sleep=None,
        utcnow=None,
        **kwargs,
    ):
        self.run_dir = Path(run_dir)
        self.sprint_id = str(sprint_id)
        self.logger = logger
        self.rig_executable = rig_executable
        self.poll_interval = poll_interval
        self._run_process = run_process or subprocess.run
        self._which = which_func or shutil.which
        self._monotonic = monotonic or time.monotonic
        self._sleep = sleep or time.sleep
        self._utcnow = utcnow or (lambda: datetime.now(timezone.utc))
        self.openrig_dir = self.run_dir / "openrig"
        self.owned_rig_ids = []
        self.released_rig_ids = []
        self._preexisting_rig_ids = set()

    # -- contract -------------------------------------------------------------

    def execute(self, request):
        deadline = self._monotonic() + request.timeout_seconds
        runtime = SUPPORTED_RUNTIMES.get(request.agent_name)
        if runtime is None:
            raise SprintRunnerError(
                "FAILED_OPENRIG_UNSUPPORTED_RUNTIME",
                f"OpenRig backend does not support agent '{request.agent_name}'; "
                f"supported: {', '.join(sorted(SUPPORTED_RUNTIMES))}",
            )
        prompt = request.metadata.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise SprintRunnerError(
                "FAILED_OPENRIG_PROTOCOL",
                "OpenRig backend requires request.metadata['prompt']",
            )

        version = self.preflight(deadline)
        rig_name = self._rig_name()
        rig_dir = self.openrig_dir / rig_name
        seat_dir = rig_dir / "seat"
        nonce = secrets.token_hex(8)
        result_file = seat_dir / f"hermes-result-{nonce}.json"
        metadata = {
            "openrig_version": version,
            "openrig_rig_name": rig_name,
            "openrig_runtime": runtime,
        }

        try:
            spec_path = self._write_spec(rig_dir, seat_dir, rig_name, runtime, request.cwd)
            rig_id, session = self._launch(spec_path, rig_name, deadline)
            metadata.update(openrig_rig_id=rig_id, openrig_session_name=session)

            ready = self._wait_until_ready(rig_name, rig_id, session, deadline)
            generation = ready["agentActivity"].get("generation")
            if not isinstance(generation, str) or not generation:
                raise SprintRunnerError(
                    "FAILED_OPENRIG_PROTOCOL",
                    f"OpenRig seat {session} reported no occupant generation",
                )
            metadata.update(openrig_node_id=ready.get("nodeId"), openrig_generation=generation)

            send_started = self._utcnow()
            self._send(session, self._task_text(prompt, request.cwd, result_file), deadline)
            send_confirmed = self._utcnow()
            started = self._wait_for_completion(
                rig_name, rig_id, session, send_started, send_confirmed, generation, deadline,
            )
            metadata["openrig_turn_started"] = started

            outcome = self._read_result(result_file)
            self._save_transcript(session, rig_dir, deadline)
        finally:
            # Covers rigs recorded by _launch even when it raised afterwards.
            for owned in list(self.owned_rig_ids):
                if owned not in self.released_rig_ids:
                    self._release_quietly(owned)

        unreleased = [r for r in self.owned_rig_ids if r not in self.released_rig_ids]
        if unreleased:
            raise SprintRunnerError(
                "FAILED_OPENRIG_UNAVAILABLE",
                f"OpenRig rig(s) {', '.join(unreleased)} could not be released and may still be running",
            )

        succeeded = outcome["status"] == "succeeded"
        envelope = {
            "type": "result",
            "subtype": "success" if succeeded else "error_during_execution",
            "is_error": not succeeded,
            "result": outcome["summary"],
            "backend": self.name,
        }
        stdout = json.dumps(envelope)
        stderr = "" if succeeded else outcome["summary"]
        request.stdout_file.parent.mkdir(parents=True, exist_ok=True)
        request.stdout_file.write_text(stdout, encoding="utf-8")
        request.stderr_file.write_text(stderr, encoding="utf-8")
        return ExecutionResult(
            command=tuple(request.command),
            returncode=0 if succeeded else 1,
            stdout=stdout,
            stderr=stderr,
            backend=self.name,
            runtime_metadata={k: v for k, v in metadata.items() if v is not None},
        )

    def cleanup(self, success=False):
        for rig_id in list(self.owned_rig_ids):
            if rig_id not in self.released_rig_ids:
                self._release(rig_id)

    # -- lifecycle steps ------------------------------------------------------

    def preflight(self, deadline):
        if self._which(self.rig_executable) is None:
            raise SprintRunnerError(
                "FAILED_OPENRIG_EXECUTABLE_MISSING",
                f"OpenRig executable was not found: {self.rig_executable}",
            )
        version_text = self._run(["--version"], deadline, "FAILED_OPENRIG_UNAVAILABLE")
        match = re.match(r"\s*(\d+\.\d+\.\d+)", version_text)
        if match is None or not match.group(1).startswith(SUPPORTED_VERSION_PREFIX):
            raise SprintRunnerError(
                "FAILED_OPENRIG_UNAVAILABLE",
                f"Unsupported OpenRig version {version_text.strip()!r}; "
                f"expected {SUPPORTED_VERSION_PREFIX}x",
            )
        rigs = self._run_json(["ps", "--json"], deadline, "FAILED_OPENRIG_UNAVAILABLE")
        if not isinstance(rigs, list):
            raise SprintRunnerError(
                "FAILED_OPENRIG_PROTOCOL", "rig ps --json did not return a list"
            )
        # Snapshot before launch: orphan recovery may only adopt rigs absent from it.
        self._preexisting_rig_ids = {
            r.get("rigId") for r in rigs if isinstance(r, dict) and r.get("rigId")
        }
        return match.group(1)

    def _write_spec(self, rig_dir, seat_dir, rig_name, runtime, worktree):
        # Imported lazily: agents -> backends -> agents.claude would be circular.
        from agents.claude import CLAUDE_GIT_MUTATION_DENIALS

        agent_dir = rig_dir / "agent"
        (agent_dir / "runtime").mkdir(parents=True, exist_ok=True)
        seat_dir.mkdir(parents=True, exist_ok=True)
        settings = {
            "permissions": {
                "allow": ["Bash", "Edit", "Write", "Read"],
                "deny": list(CLAUDE_GIT_MUTATION_DENIALS),
                "additionalDirectories": [str(Path(worktree).resolve())],
            }
        }
        _write_json(agent_dir / "runtime" / "hermes-settings.fragment.json", settings)
        _write_json(
            agent_dir / "runtime" / "claude-activity-hooks.json",
            {"openrig_activity_hooks": True},
        )
        # JSON is valid YAML; serializing avoids hand-built YAML injection.
        _write_json(agent_dir / "agent.yaml", {
            "name": "hermes-worker",
            "version": "1.0",
            "description": "Hermes-owned single-task worker seat",
            "defaults": {"runtime": runtime, "lifecycle": {"restore_policy": "relaunch_fresh"}},
            "profiles": {"default": {"uses": {
                "skills": [], "guidance": [], "subagents": [], "plugins": [],
                "runtime_resources": ["hermes-settings", "activity-hooks"],
            }}},
            "resources": {"runtime_resources": [
                {"id": "hermes-settings", "path": "runtime/hermes-settings.fragment.json",
                 "runtime": runtime, "type": "claude_settings_fragment"},
                {"id": "activity-hooks", "path": "runtime/claude-activity-hooks.json",
                 "runtime": runtime, "type": "claude_activity_hooks"},
            ]},
            "startup": {"files": [], "actions": []},
        })
        spec_path = rig_dir / "rig.yaml"
        _write_json(spec_path, {
            "version": "0.2",
            "name": rig_name,
            "pods": [{
                "id": "hermes",
                "label": "Hermes worker",
                "members": [{
                    "id": "worker",
                    "agent_ref": f"path:{agent_dir.resolve()}",
                    "profile": "default",
                    "runtime": runtime,
                    "cwd": str(seat_dir.resolve()),
                }],
                "edges": [],
            }],
            "edges": [],
        })
        return spec_path

    def _launch(self, spec_path, rig_name, deadline):
        try:
            payload = self._run_json(
                ["up", str(spec_path), "--json"], deadline, "FAILED_OPENRIG_CREATE",
                allow_failure_payload=True,
            )
        except SprintRunnerError:
            # The daemon may have created the rig even though its response was lost.
            self._adopt_orphan(rig_name)
            raise
        if not (isinstance(payload, dict) and payload.get("rigId")):
            self._adopt_orphan(rig_name)
        rig_id = payload.get("rigId") if isinstance(payload, dict) else None
        if isinstance(rig_id, str) and rig_id:
            # Track ownership before validating anything else so cleanup can release it.
            self.owned_rig_ids.append(rig_id)
        if (
            not isinstance(rig_id, str)
            or not rig_id
            or payload.get("status") != "completed"
            or payload.get("errors")
        ):
            raise SprintRunnerError(
                "FAILED_OPENRIG_CREATE",
                f"rig up did not complete: {_brief(payload)}",
            )
        session = None
        for stage in payload.get("stages") or []:
            detail = stage.get("detail") if isinstance(stage, dict) else None
            if not isinstance(detail, dict) or stage.get("stage") != "import_rig":
                continue
            if detail.get("rigId") != rig_id or detail.get("specName") != rig_name:
                raise SprintRunnerError(
                    "FAILED_OPENRIG_PROTOCOL", "rig up reported a different rig than requested"
                )
            for node in detail.get("nodes") or []:
                if isinstance(node, dict) and node.get("logicalId") == WORKER_LOGICAL_ID:
                    session = node.get("sessionName")
        if not isinstance(session, str) or not session:
            raise SprintRunnerError(
                "FAILED_OPENRIG_PROTOCOL", "rig up did not report the worker session"
            )
        self._log("info", "OpenRig rig %s (%s) launched", rig_name, rig_id)
        return rig_id, session

    def _adopt_orphan(self, rig_name):
        """Record a rig created under our name whose ID `rig up` never returned.

        Only a rig that is new since the pre-launch snapshot and carries our random
        name is adopted; release is still by exact rigId. Retries are bounded by one
        shared budget so recovery cannot extend a timed-out request indefinitely.
        """
        budget = self._monotonic() + ORPHAN_RECOVERY_SECONDS
        for attempt in range(ORPHAN_RECOVERY_ATTEMPTS):
            if attempt:
                remaining = budget - self._monotonic()
                if remaining <= 0:
                    break
                self._sleep(min(self.poll_interval, remaining))
            try:
                rigs = self._run_json(["ps", "--json"], budget, "FAILED_OPENRIG_UNAVAILABLE")
            except SprintRunnerError as exc:
                self._log("warning", "Orphan check for OpenRig rig %s failed: %s", rig_name, exc.message)
                continue
            if not isinstance(rigs, list):
                continue
            matches = [
                r.get("rigId") for r in rigs
                if isinstance(r, dict) and r.get("name") == rig_name
                and r.get("rigId") not in self._preexisting_rig_ids
            ]
            if len(matches) == 1 and isinstance(matches[0], str) and matches[0]:
                if matches[0] not in self.owned_rig_ids:
                    self.owned_rig_ids.append(matches[0])
                return
        self._log("error", "Could not confirm whether OpenRig rig %s was created", rig_name)

    def _wait_until_ready(self, rig_name, rig_id, session, deadline):
        while True:
            node = self._node(rig_name, rig_id, session, deadline)
            if node is None:
                raise SprintRunnerError(
                    "FAILED_OPENRIG_SESSION_LOST", f"OpenRig seat {session} disappeared during startup"
                )
            startup = node.get("startupStatus")
            activity = node.get("agentActivity") or {}
            if startup in ("attention_required", "failed"):
                raise SprintRunnerError(
                    "FAILED_OPENRIG_SEAT_NOT_READY",
                    f"OpenRig seat {session} startup {startup}: {node.get('latestError') or 'no detail'}",
                )
            if activity.get("state") == "needs_input":
                raise SprintRunnerError(
                    "FAILED_OPENRIG_SEAT_NOT_READY",
                    f"OpenRig seat {session} needs input during startup ({activity.get('reason')})",
                )
            if startup == "ready" and _hook_event(activity, "Stop", "idle"):
                return node
            self._pause(deadline, f"OpenRig seat {session} did not become ready")

    def _send(self, session, text, deadline):
        idle_wait = max(1, min(SEND_IDLE_WAIT_SECONDS, int(self._remaining(deadline))))
        payload = self._run_json(
            ["send", "--wait-for-idle", str(idle_wait), "--json", "--", session, text],
            deadline, "FAILED_OPENRIG_DELIVERY", allow_failure_payload=True,
        )
        if not isinstance(payload, dict) or payload.get("ok") is not True or payload.get("sent") is not True:
            raise SprintRunnerError(
                "FAILED_OPENRIG_DELIVERY", f"rig send was not delivered: {_brief(payload)}"
            )

    def _wait_for_completion(
        self, rig_name, rig_id, session, send_started, send_confirmed, generation, deadline,
    ):
        """Return True if the turn start was observed.

        A Stop proves completion only if it follows evidence of our turn: either a
        UserPromptSubmit after the send began, or (start missed) the confirmed send itself.
        """
        prompt_at = None
        while True:
            node = self._node(rig_name, rig_id, session, deadline)
            if node is None or node.get("sessionStatus") != "running":
                raise SprintRunnerError(
                    "FAILED_OPENRIG_SESSION_LOST", f"OpenRig seat {session} is no longer running"
                )
            activity = node.get("agentActivity") or {}
            if activity.get("state") == "needs_input":
                raise SprintRunnerError(
                    "FAILED_OPENRIG_NEEDS_INPUT",
                    f"OpenRig seat {session} is blocked on input ({activity.get('reason')})",
                )
            if _is_hook(activity):
                if activity.get("generation") != generation:
                    raise SprintRunnerError(
                        "FAILED_OPENRIG_SESSION_LOST",
                        f"OpenRig seat {session} changed occupant generation mid-task",
                    )
                event_at = _parse_time(activity.get("eventAt"))
                if event_at is not None:
                    if _hook_event(activity, "UserPromptSubmit", "running") and event_at > send_started:
                        prompt_at = event_at
                    elif _hook_event(activity, "Stop", "idle") and event_at > (prompt_at or send_confirmed):
                        return prompt_at is not None
            self._pause(deadline, f"OpenRig seat {session} did not finish the task")

    def _read_result(self, result_file):
        try:
            data = json.loads(result_file.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SprintRunnerError(
                "FAILED_OPENRIG_PROTOCOL",
                "OpenRig turn finished without writing the Hermes result file",
            ) from exc
        except (OSError, ValueError) as exc:  # JSONDecodeError, UnicodeDecodeError
            raise SprintRunnerError(
                "FAILED_OPENRIG_PROTOCOL", "Hermes result file is not valid JSON"
            ) from exc
        if (
            not isinstance(data, dict)
            or data.get("status") not in ("succeeded", "failed")
            or not isinstance(data.get("summary"), str)
        ):
            raise SprintRunnerError(
                "FAILED_OPENRIG_PROTOCOL",
                "Hermes result file must be {status: succeeded|failed, summary: str}",
            )
        return data

    def _save_transcript(self, session, rig_dir, deadline):
        try:
            payload = self._run_json(
                ["transcript", session, "--json", "--tail", "200"], deadline,
                "FAILED_OPENRIG_UNAVAILABLE",
            )
            content = payload.get("content") if isinstance(payload, dict) else None
            if isinstance(content, str):
                (rig_dir / "transcript.txt").write_text(content, encoding="utf-8")
        except SprintRunnerError as exc:
            # Diagnostics only; the result is already proven.
            self._log("warning", "OpenRig transcript capture failed: %s", exc.message)

    def _release(self, rig_id):
        payload = self._run_json(
            ["down", rig_id, "--delete", "--force", "--json"],
            self._monotonic() + RELEASE_TIMEOUT_SECONDS,
            "FAILED_OPENRIG_UNAVAILABLE",
            allow_failure_payload=True,
        )
        already_gone = (
            isinstance(payload, dict)
            and isinstance(payload.get("error"), dict)
            and "No rig found" in str(payload["error"].get("fact", ""))
        )
        if not already_gone and (
            not isinstance(payload, dict)
            or payload.get("rigId") != rig_id
            or payload.get("errors")
        ):
            raise SprintRunnerError(
                "FAILED_OPENRIG_UNAVAILABLE", f"rig down {rig_id} failed: {_brief(payload)}"
            )
        self.released_rig_ids.append(rig_id)
        self._log("info", "OpenRig rig %s released", rig_id)

    def _release_quietly(self, rig_id):
        try:
            self._release(rig_id)
        except SprintRunnerError as exc:
            # Left in owned_rig_ids for cleanup() to retry.
            self._log("error", "OpenRig release of %s failed: %s", rig_id, exc.message)

    # -- helpers --------------------------------------------------------------

    def _node(self, rig_name, rig_id, session, deadline):
        nodes = self._run_json(
            ["ps", "--nodes", "--json", "--full", "--rig", rig_name], deadline,
            "FAILED_OPENRIG_UNAVAILABLE",
        )
        if not isinstance(nodes, list):
            raise SprintRunnerError("FAILED_OPENRIG_PROTOCOL", "rig ps --nodes did not return a list")
        for node in nodes:
            if not isinstance(node, dict) or node.get("canonicalSessionName") != session:
                continue
            if node.get("rigId") != rig_id:
                raise SprintRunnerError(
                    "FAILED_OPENRIG_PROTOCOL",
                    f"Session {session} belongs to rig {node.get('rigId')}, not owned rig {rig_id}",
                )
            return node
        return None

    def _task_text(self, prompt, worktree, result_file):
        return (
            f"{prompt}\n\n"
            "--- Hermes result protocol ---\n"
            f"Work only inside {Path(worktree).resolve()}. When you are completely finished, "
            f"use the Write tool to create {result_file.resolve()} containing a JSON object "
            '{"status": "succeeded" or "failed", "summary": "<one sentence>"}. '
            "Write that file last, exactly once."
        )

    def _rig_name(self):
        slug = re.sub(r"[^a-z0-9-]+", "-", self.sprint_id.lower()).strip("-")[:24] or "task"
        return f"hermes-{slug}-{secrets.token_hex(4)}"

    def _remaining(self, deadline):
        return deadline - self._monotonic()

    def _pause(self, deadline, what):
        remaining = self._remaining(deadline)
        if remaining <= 0:
            raise SprintRunnerError("FAILED_TIMEOUT", f"{what} before the task timeout")
        self._sleep(min(self.poll_interval, remaining))

    def _run(self, args, deadline, failure_code, allow_failure_payload=False):
        remaining = self._remaining(deadline)
        if remaining <= 0:
            raise SprintRunnerError("FAILED_TIMEOUT", f"OpenRig task timed out before rig {args[0]}")
        try:
            result = self._run_process(
                [self.rig_executable, *args],
                capture_output=True,
                text=True,
                timeout=remaining,
            )
        except FileNotFoundError as exc:
            raise SprintRunnerError(
                "FAILED_OPENRIG_EXECUTABLE_MISSING",
                f"OpenRig executable was not found: {self.rig_executable}",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SprintRunnerError(
                "FAILED_TIMEOUT", f"OpenRig command rig {args[0]} exceeded the task timeout"
            ) from exc
        except OSError as exc:
            raise SprintRunnerError(
                "FAILED_OPENRIG_UNAVAILABLE", f"Could not run rig {args[0]}: {exc}"
            ) from exc
        if result.returncode != 0 and not allow_failure_payload:
            detail = (result.stderr or result.stdout or "unknown error").strip()[:500]
            raise SprintRunnerError(failure_code, f"rig {args[0]} failed: {detail}")
        return result.stdout or ""

    def _run_json(self, args, deadline, failure_code, allow_failure_payload=False):
        text = self._run(args, deadline, failure_code, allow_failure_payload)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise SprintRunnerError(
                "FAILED_OPENRIG_PROTOCOL", f"rig {args[0]} returned malformed JSON"
            ) from exc

    def _log(self, level, message, *args):
        if self.logger is not None:
            getattr(self.logger, level)(message, *args)


def _is_hook(activity):
    return (
        activity.get("evidenceSource") == "runtime_hook"
        and activity.get("stale") is False
        and activity.get("fallback") is False
    )


def _hook_event(activity, raw_event, state):
    return _is_hook(activity) and activity.get("rawEvent") == raw_event and activity.get("state") == state


def _parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _brief(payload):
    return json.dumps(payload)[:300] if payload is not None else "no payload"


def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
