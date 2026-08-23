import json
import logging
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from typing import Any, Dict, Optional, Set

from events.event_bus import event_bus
from jobs.job_service import job_service
from jobs.job_state_reducer import job_state_reducer

logger = logging.getLogger("hermes.job_launcher")

SPRINT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


class JobLauncher:
    """
    Safely executes registered Hermes sprint definitions via the authoritative sprint runner.
    Prevents arbitrary command execution, path traversal, or unapproved script execution.
    Provides process-group management, output draining, and truthful cancellation.
    """

    def __init__(
        self,
        sprints_dir: Optional[Path] = None,
        runner_script: Optional[Path] = None,
        control_url: Optional[str] = None,
    ):
        self.root_dir = Path(__file__).resolve().parent.parent
        self.sprints_dir = sprints_dir or (self.root_dir / "sprints")
        self.runner_script = runner_script or (self.root_dir / "runner" / "run-hermes-sprint.py")
        self._configured_control_url = control_url
        self._active_processes: Dict[str, subprocess.Popen] = {}
        self._process_logs: Dict[str, Any] = {}

    @property
    def control_url(self) -> str:
        return self._configured_control_url or os.environ.get("LYSSTACK_CONTROL_URL", "http://127.0.0.1:8000")

    @control_url.setter
    def control_url(self, value: Optional[str]):
        self._configured_control_url = value

    def reap_finished(self):
        """Reaps exited processes and closes open log file descriptors."""
        finished_ids = []
        for j_id, proc in list(self._active_processes.items()):
            if proc.poll() is not None:
                finished_ids.append(j_id)
                f = self._process_logs.pop(j_id, None)
                if f and hasattr(f, "close") and not getattr(f, "closed", True):
                    try:
                        f.close()
                    except Exception:
                        pass
        for j_id in finished_ids:
            self._active_processes.pop(j_id, None)

    def get_registered_sprints(self) -> Set[str]:
        """Returns the set of approved registered sprint IDs."""
        if not self.sprints_dir.exists():
            return set()
        return {f.stem for f in self.sprints_dir.glob("*.json")}

    def launch(
        self,
        sprint_id: str,
        dry_run: bool = False,
        skip_agent_exec: bool = False,
        control_url_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Launches an approved sprint execution in a managed runner subprocess with safe output draining.
        """
        self.reap_finished()

        if not SPRINT_ID_PATTERN.match(sprint_id):
            raise ValueError(f"Invalid sprint ID format: '{sprint_id}'")

        spec_file = (self.sprints_dir / f"{sprint_id}.json").resolve()
        if not spec_file.exists() or not str(spec_file).startswith(str(self.sprints_dir.resolve())):
            raise ValueError(f"Unknown or unapproved sprint ID: '{sprint_id}'")

        with open(spec_file, "r", encoding="utf-8") as f:
            spec = json.load(f)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        job_id = f"run_{timestamp}_{sprint_id}"

        # Pre-register job in JobService
        job_state_reducer.apply(
            kind="job.created",
            detail=f"Sprint {sprint_id} queued for execution",
            job_id=job_id,
            metadata={
                "sprintId": sprint_id,
                "title": spec.get("name", f"Hermes Sprint {sprint_id}"),
                "repository": spec.get("target_repo", "—"),
                "branch": spec.get("target_branch", f"hermes/{sprint_id}/integration"),
                "priority": "P1",
                "phases": spec.get("phases", []),
            },
        )

        cmd = [
            sys.executable,
            str(self.runner_script),
            "--spec",
            str(spec_file),
        ]
        if dry_run:
            cmd.append("--dry-run")
        if skip_agent_exec:
            cmd.append("--skip-agent-execution")

        target_control_url = control_url_override or self.control_url
        env = dict(os.environ)
        env["LYSSTACK_CONTROL_URL"] = target_control_url
        env["HERMES_JOB_ID"] = job_id

        log_dir = self.root_dir / "hermes-runs" / "launcher_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = open(log_dir / f"{job_id}.log", "w", encoding="utf-8")

        # Use start_new_session so the runner and its children form a distinct process group for clean cancellation
        proc = subprocess.Popen(
            cmd,
            cwd=str(self.root_dir),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        self._active_processes[job_id] = proc
        self._process_logs[job_id] = log_file
        logger.info("Launched sprint %s as PID %s in PGID %s (Job ID: %s)", sprint_id, proc.pid, proc.pid, job_id)

        return {
            "jobId": job_id,
            "sprintId": sprint_id,
            "status": "PREPARING",
            "pid": proc.pid,
        }

    def cancel(self, job_id: str) -> bool:
        """
        Cleanly terminates an active runner process group.
        Never claims cancellation without actually killing an owned active execution.
        """
        self.reap_finished()
        proc = self._active_processes.get(job_id)
        if not proc or proc.poll() is not None:
            # Process not running or not owned
            return False

        killed_successfully = False
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
            try:
                proc.wait(timeout=2.0)
                killed_successfully = True
            except subprocess.TimeoutExpired:
                os.killpg(pgid, signal.SIGKILL)
                proc.wait(timeout=1.0)
                killed_successfully = True
        except ProcessLookupError:
            # Process already exited
            killed_successfully = True
        except Exception as exc:
            logger.warning("Error cancelling process group %s (PID %s): %s", job_id, proc.pid, exc)
            return False
        finally:
            self._active_processes.pop(job_id, None)
            f = self._process_logs.pop(job_id, None)
            if f and hasattr(f, "close") and not getattr(f, "closed", True):
                try:
                    f.close()
                except Exception:
                    pass

        if killed_successfully:
            job_state_reducer.apply(
                kind="job.cancelled",
                detail=f"Job {job_id} process terminated by operator",
                job_id=job_id,
            )

            event_bus.publish(
                source_id="lysstack",
                source_kind="runtime",
                source_name="JobLauncher",
                kind="job.cancelled",
                detail=f"Job {job_id} cancelled by operator",
                job_id=job_id,
            )
            return True

        return False


job_launcher = JobLauncher()
