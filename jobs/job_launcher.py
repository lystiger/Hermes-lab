import asyncio
import json
import logging
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Set

from events.event_bus import event_bus
from jobs.job_service import job_service
from jobs.job_state_reducer import job_state_reducer
from runtime.engine import ReactiveJobEngine
from runtime.job_state import JobRecord, JobState
from runtime.task_graph import TaskNode
from runtime.hermes_adapter import HermesActorAdapter, HermesVerifierAdapter
from runtime.events import RuntimeEventBridge
from runtime.limits import RuntimeLimits

logger = logging.getLogger("hermes.job_launcher")

SPRINT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


class JobLauncher:
    """
    Authoritative job orchestrator and execution launcher.
    Integrates ReactiveJobEngine as the production runtime while preserving
    execution compatibility with low-level Hermes backends and tools.
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
        self._active_async_tasks: Dict[str, asyncio.Task] = {}
        self._active_threads: Dict[str, threading.Thread] = {}

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

        for j_id, task in list(self._active_async_tasks.items()):
            if task.done():
                self._active_async_tasks.pop(j_id, None)

    def get_registered_sprints(self) -> Set[str]:
        """Returns the set of approved registered sprint IDs."""
        if not self.sprints_dir.exists():
            return set()
        return {f.stem for f in self.sprints_dir.glob("*.json")}

    def _start_engine_background(self, engine: ReactiveJobEngine) -> None:
        job_id = engine.job.job_id

        async def _run_loop():
            try:
                await engine.run_until_complete()
            except Exception as exc:
                logger.exception("Reactive engine %s encountered runtime exception: %s", job_id, exc)

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(_run_loop(), name=f"reactive-engine-{job_id}")
            self._active_async_tasks[job_id] = task
        except RuntimeError:
            # No running event loop in current thread; launch dedicated background worker thread
            def _thread_worker():
                asyncio.run(_run_loop())

            th = threading.Thread(target=_thread_worker, name=f"reactive-engine-th-{job_id}", daemon=True)
            th.start()
            self._active_threads[job_id] = th

    def _launch_legacy(
        self,
        sprint_id: str,
        spec: Dict[str, Any],
        spec_file: Path,
        job_id: str,
        dry_run: bool = False,
        skip_agent_exec: bool = False,
        control_url_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        job_state_reducer.apply(
            kind="job.created",
            detail=f"Sprint {sprint_id} queued for execution (legacy runner)",
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
        logger.info("Launched sprint %s via legacy runner (PID %s, Job ID: %s)", sprint_id, proc.pid, job_id)

        return {
            "jobId": job_id,
            "sprintId": sprint_id,
            "status": "PREPARING",
            "pid": proc.pid,
            "mode": "legacy_static_runner",
        }

    def launch(
        self,
        sprint_id: str,
        dry_run: bool = False,
        skip_agent_exec: bool = False,
        control_url_override: Optional[str] = None,
        mode: str = "reactive_runtime",
    ) -> Dict[str, Any]:
        """
        Launches an approved sprint execution using the authoritative ReactiveJobEngine runtime.
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

        if mode == "legacy_static_runner":
            return self._launch_legacy(
                sprint_id=sprint_id,
                spec=spec,
                spec_file=spec_file,
                job_id=job_id,
                dry_run=dry_run,
                skip_agent_exec=skip_agent_exec,
                control_url_override=control_url_override,
            )

        # Build production ReactiveJobEngine
        event_bridge = RuntimeEventBridge(event_bus)

        # Decompose initial tasks from sprint spec phases
        initial_tasks: List[TaskNode] = []
        phases = spec.get("phases", [])
        for idx, p in enumerate(phases, start=1):
            phase_id = p.get("name") or f"phase_{idx}"
            agent_id = p.get("agent")
            req_caps = p.get("required_capabilities") or []
            t = TaskNode(
                task_id=phase_id,
                job_id=job_id,
                description=p.get("prompt_file") or p.get("name") or f"Execute sprint phase {idx}",
                assigned_actor=agent_id,
                required_capabilities=req_caps,
                metadata={"phase": p, "order": idx, "timeout_seconds": p.get("timeout_seconds")},
            )
            if p.get("dependencies"):
                t.dependencies = list(p["dependencies"])
            elif idx > 1:
                t.dependencies = [phases[idx - 2].get("name") or f"phase_{idx - 1}"]

            initial_tasks.append(t)

        actor_adapter = HermesActorAdapter(
            target_repo=self.root_dir,
            dry_run=dry_run,
            skip_agent_exec=skip_agent_exec,
        )

        verifier_adapter = HermesVerifierAdapter(
            verification_steps=spec.get("verification_steps") or spec.get("verification", []),
            working_dir=self.root_dir,
        )

        engine = ReactiveJobEngine(
            job_id=job_id,
            goal=spec.get("name", f"Hermes Sprint {sprint_id}"),
            title=spec.get("name", f"Hermes Sprint {sprint_id}"),
            repository=spec.get("target_repo", "—"),
            branch=spec.get("target_branch", f"hermes/{sprint_id}/integration"),
            priority="P1",
            actor_adapter=actor_adapter,
            verifier=verifier_adapter,
            limits=RuntimeLimits(
                concurrency_limit=spec.get("limits", {}).get("concurrency_limit", 3),
                max_task_attempts=spec.get("limits", {}).get("max_attempts_per_task", 3),
            ),
            event_bridge=event_bridge,
        )

        # Register engine with JobService BEFORE execution begins
        job_service.register_engine(engine)

        # Seed initial tasks into engine graph
        for t in initial_tasks:
            try:
                engine.graph.add_task(t)
            except ValueError:
                pass

        # Sync initial state with job_state_reducer
        job_state_reducer.apply(
            kind="job.created",
            detail=f"Sprint {sprint_id} initialized with reactive runtime engine",
            job_id=job_id,
            metadata={
                "sprintId": sprint_id,
                "title": spec.get("name", f"Hermes Sprint {sprint_id}"),
                "repository": spec.get("target_repo", "—"),
                "branch": spec.get("target_branch", f"hermes/{sprint_id}/integration"),
                "priority": "P1",
                "phases": phases,
            },
        )

        # Start execution loop asynchronously in background
        self._start_engine_background(engine)
        logger.info("Launched reactive job %s for sprint %s (mode: %s)", job_id, sprint_id, mode)

        return {
            "jobId": job_id,
            "sprintId": sprint_id,
            "status": engine.job.state.value.upper(),
            "mode": mode,
        }

    def cancel(self, job_id: str) -> bool:
        """
        Cleanly terminates an active job (reactive engine or legacy process).
        """
        self.reap_finished()

        # 1. Check active ReactiveJobEngine
        engine = job_service.get_engine(job_id)
        if engine and not engine.is_terminal:
            engine.job.transition_to(
                JobState.CANCELLED,
                reason="Job cancelled by operator",
                event_bridge=engine.event_bridge,
            )
            task = self._active_async_tasks.pop(job_id, None)
            if task and not task.done():
                task.cancel()

            job_state_reducer.apply(
                kind="job.cancelled",
                detail=f"Job {job_id} cancelled by operator",
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

        # 2. Check legacy runner process
        proc = self._active_processes.get(job_id)
        if not proc or proc.poll() is not None:
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
