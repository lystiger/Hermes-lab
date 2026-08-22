import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Dict, Optional, Set

from event_bus import event_bus
from job_service import job_service, JobDetailDTO, JobPhaseDTO
from job_state_reducer import job_state_reducer

logger = logging.getLogger("hermes.job_launcher")

SPRINT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


class JobLauncher:
    """
    Safely executes registered Hermes sprint definitions via the authoritative sprint runner.
    Prevents arbitrary command execution, path traversal, or unapproved script execution.
    """

    def __init__(
        self,
        sprints_dir: Optional[Path] = None,
        runner_script: Optional[Path] = None,
        control_url: str = "http://127.0.0.1:8000",
    ):
        self.root_dir = Path(__file__).resolve().parent
        self.sprints_dir = sprints_dir or (self.root_dir / "sprints")
        self.runner_script = runner_script or (self.root_dir / "runner" / "run-hermes-sprint.py")
        self.control_url = control_url
        self._active_processes: Dict[str, subprocess.Popen] = {}

    def get_registered_sprints(self) -> Set[str]:
        """Returns the set of approved registered sprint IDs."""
        if not self.sprints_dir.exists():
            return set()
        return {f.stem for f in self.sprints_dir.glob("*.json")}

    def launch(self, sprint_id: str, dry_run: bool = False, skip_agent_exec: bool = False) -> Dict[str, Any]:
        """
        Launches an approved sprint execution in a managed runner subprocess.
        """
        if not SPRINT_ID_PATTERN.match(sprint_id):
            raise ValueError(f"Invalid sprint ID format: '{sprint_id}'")

        spec_file = (self.sprints_dir / f"{sprint_id}.json").resolve()
        if not spec_file.exists() or not str(spec_file).startswith(str(self.sprints_dir.resolve())):
            raise ValueError(f"Unknown or unapproved sprint ID: '{sprint_id}'")

        # Load spec to pre-register job
        with open(spec_file, "r", encoding="utf-8") as f:
            spec = json.load(f)

        import time
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
                "repository": spec.get("target_repo", "Target Repo"),
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

        env = dict(os.environ)
        env["LYSSTACK_CONTROL_URL"] = self.control_url
        env["HERMES_JOB_ID"] = job_id

        proc = subprocess.Popen(
            cmd,
            cwd=str(self.root_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self._active_processes[job_id] = proc
        logger.info("Launched sprint %s as PID %s (Job ID: %s)", sprint_id, proc.pid, job_id)

        return {
            "jobId": job_id,
            "sprintId": sprint_id,
            "status": "PREPARING",
            "pid": proc.pid,
        }

    def cancel(self, job_id: str) -> bool:
        """Cleanly terminates an active runner process."""
        proc = self._active_processes.get(job_id)
        if not proc:
            job = job_service.get_job(job_id)
            if job and job.status in {"RUNNING", "PREPARING", "QUEUED"}:
                job_state_reducer.apply(
                    kind="job.cancelled",
                    detail=f"Job {job_id} cancelled by operator",
                    job_id=job_id,
                )
                return True
            return False

        try:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1.0)
        except Exception as exc:
            logger.warning("Error cancelling process %s: %s", job_id, exc)
        finally:
            self._active_processes.pop(job_id, None)

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


job_launcher = JobLauncher()
