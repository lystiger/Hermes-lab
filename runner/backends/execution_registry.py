"""In-process view of live execution resources, built from the D-009 event stream.

The registry holds what this process has seen. `build_execution_snapshot()` adds read-only
backend status, including the OpenRig ledger, which covers rigs left by earlier processes.
Nothing here runs a mutating command.
"""

import json
import logging
import os
import shutil
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import events
from .openrig_backend import describe_openrig

logger = logging.getLogger("hermes.runner.backends.execution_registry")

# Resource state after each event. Events not listed here leave the state unchanged.
_STATE_FOR_EVENT = {
    events.RESOURCE_ACQUIRED: "acquiring",
    events.RESOURCE_READY: "ready",
    events.RUNNING: "running",
    events.FAILED: "releasing",
    events.CANCELLED: "releasing",
    events.RESOURCE_POOLED: "idle",
    events.RELEASE_FAILED: "failed",
}
# Event metadata copied into a resource's `details`. Keys match the D-009 wire names.
_DETAIL_KEYS = ("reused", "generation", "sessionName", "nodeId", "rigId", "errorCode", "error")


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# A restored row that no event has refreshed is dropped after this long (its owner may be gone).
RESTORED_TTL = timedelta(minutes=30)
STATE_PATH_ENV = "HERMES_EXECUTION_STATE"


def default_state_path():
    override = os.environ.get(STATE_PATH_ENV)
    if override:
        return Path(override)
    state_home = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(state_home) / "hermes" / "execution-registry.json"


class ExecutionRegistry:
    """Thread-safe. Events arrive from backend worker threads and timer threads.

    In-memory by default. The API server calls enable_persistence() so the Execution page survives
    a restart: rows are saved after every change and reloaded flagged `details.restored`. A restored
    row is not trusted: OpenRig rows whose rig the daemon no longer knows are pruned at snapshot
    time, and any restored row not refreshed by an event within RESTORED_TTL is dropped.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._resources = {}
        self._executions = {}
        self._path = None
        self._save_lock = threading.Lock()
        # Saves run on one background thread: apply() only marks the state dirty, so slow storage
        # never delays an execution worker, and bursts of events coalesce into one write.
        self._dirty = threading.Condition(threading.Lock())
        self._pending_saves = 0
        self._writing = False
        self._writer = None

    def register_execution(self, execution_id, job_id, handle, cancel):
        """Keep live owned handles separate from serializable resource rows."""
        with self._lock:
            self._executions[execution_id] = (job_id, handle, cancel)

    def unregister_execution(self, execution_id):
        with self._lock:
            self._executions.pop(execution_id, None)

    def cancel_execution(self, execution_id):
        with self._lock:
            entry = self._executions.get(execution_id)
        if entry is None:
            return False
        entry[2]()
        return True

    def cancel_job(self, job_id):
        with self._lock:
            callbacks = [row[2] for row in self._executions.values() if row[0] == job_id]
        for callback in callbacks:
            try:
                callback()
            except Exception:
                logger.warning("Execution cancellation failed", exc_info=True)

    def enable_persistence(self, path=None):
        self._path = Path(path) if path is not None else default_state_path()
        try:
            rows = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            rows = []
        except (OSError, ValueError):
            logger.warning("Execution state %s unreadable; starting empty", self._path, exc_info=True)
            rows = []
        with self._lock:
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict) or not all(row.get(k) for k in ("backend", "kind", "id")):
                    continue
                details = dict(row.get("details") or {})
                details["restored"] = True
                # Keep the first restore time across restarts, so a stale row keeps ageing toward expiry.
                row = dict(row, details=details, restoredAt=row.get("restoredAt") or _now())
                self._resources[(row["backend"], row["kind"], row["id"])] = row
        self._prune_expired()
        self._writer = threading.Thread(target=self._write_loop, name="hermes-execution-state", daemon=True)
        self._writer.start()
        self._save()  # persist the restore times and any expiry

    def _save(self):
        """Schedule a save (non-blocking)."""
        if self._path is None:
            return
        with self._dirty:
            self._pending_saves += 1
            self._dirty.notify()

    def _write_loop(self):
        while True:
            with self._dirty:
                while self._pending_saves == 0:
                    self._dirty.wait()
                self._pending_saves = 0
                self._writing = True  # set atomically with taking the work, so flush() sees it
            try:
                self._save_now()
            finally:
                with self._dirty:
                    self._writing = False
                    self._dirty.notify_all()

    def flush(self, timeout=5.0):
        """Wait until scheduled saves are written (tests, shutdown)."""
        if self._path is None or self._writer is None:
            return
        deadline = time.monotonic() + timeout
        with self._dirty:
            # Done only when nothing is queued AND no write is in progress, all within one timeout.
            while self._pending_saves or self._writing:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    logger.warning("Execution state flush timed out; the last changes may not be on disk")
                    return False
                self._dirty.wait(timeout=min(0.05, remaining))
        return True

    def _save_now(self):
        if self._path is None:
            return
        # Snapshot and write under one lock, so a slower save can never overwrite a newer state.
        with self._save_lock:
            with self._lock:
                rows = [dict(row, details=dict(row["details"])) for row in self._resources.values()]
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(dir=self._path.parent, prefix=".execution-", suffix=".tmp")
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(rows, handle)
                os.replace(tmp, self._path)
            except OSError:
                # Persistence is a convenience for restarts; it must never affect execution.
                logger.warning("Execution state not saved to %s", self._path, exc_info=True)

    def _prune_expired(self):
        cutoff = datetime.now(timezone.utc) - RESTORED_TTL
        removed = False
        with self._lock:
            for key, row in list(self._resources.items()):
                restored_at = row.get("restoredAt")
                if restored_at and _parse(restored_at) < cutoff:
                    del self._resources[key]
                    removed = True
        if removed:
            self._save()  # an expired row must not come back after the next restart

    def prune_restored_rigs(self, live_rig_ids):
        """Drop restored OpenRig rows whose rig the daemon no longer knows."""
        removed = False
        with self._lock:
            for key, row in list(self._resources.items()):
                if row.get("restoredAt") and row["backend"] == "openrig":
                    rig_id = row["details"].get("rigId") or row["id"]
                    if rig_id not in live_rig_ids:
                        del self._resources[key]
                        removed = True
        if removed:
            self._save()

    def apply(self, event):
        metadata = event.metadata
        resource = metadata.get("resource")
        if not isinstance(resource, dict):
            return
        key = (metadata.get("backend"), resource.get("kind"), resource.get("id"))
        with self._lock:
            if event.kind == events.RESOURCE_RELEASED:
                self._resources.pop(key, None)
                changed = True
            else:
                changed = False
        if changed:
            self._save()
            return
        with self._lock:
            entry = self._resources.get(key)
            if entry is None:
                entry = {
                    "backend": key[0], "kind": key[1], "id": key[2], "label": key[2],
                    "state": None, "jobId": None, "taskId": None, "executionId": None,
                    "since": None, "expiresAt": None, "details": {},
                }
                self._resources[key] = entry
            entry["label"] = resource.get("label") or entry["label"]
            entry["executionId"] = metadata.get("executionId")
            if event.job_id:
                entry["jobId"] = event.job_id
            if getattr(event, "task_id", None):
                entry["taskId"] = event.task_id
            if event.kind == events.RESOURCE_ACQUIRED:
                # A new attempt must not inherit the previous failure.
                for name in ("errorCode", "error", "releaseFailed"):
                    entry["details"].pop(name, None)
            for name in _DETAIL_KEYS:
                if name in metadata:
                    entry["details"][name] = metadata[name]
            if event.kind == events.RELEASE_FAILED:
                entry["details"]["releaseFailed"] = True
            state = _STATE_FOR_EVENT.get(event.kind)
            if state is not None:
                if state != entry["state"]:
                    entry["since"] = _now()
                entry["state"] = state
                entry["expiresAt"] = metadata.get("expiresAt") if state == "idle" else None
            # A live event proves the row is current again.
            entry.pop("restoredAt", None)
            entry["details"].pop("restored", None)
        self._save()

    def resources(self):
        self._prune_expired()
        with self._lock:
            rows = [dict(row, details=dict(row["details"])) for row in self._resources.values()]
        return sorted(rows, key=lambda row: row["since"] or "")


default_execution_registry = ExecutionRegistry()


def _parse(stamp):
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def probe_backends(*, which=None, run_process=None, ledger=None, live_rig_ids=None):
    """Read-only availability of each backend, plus the OpenRig status (None when rig is absent)."""
    which = which or shutil.which
    herdr_found = which("herdr") is not None
    backends = [
        {"name": "subprocess", "available": True, "detail": "local child process"},
        {
            "name": "herdr",
            "available": herdr_found,
            "detail": "herdr executable on PATH" if herdr_found else "herdr executable not found",
        },
    ]
    try:
        openrig = describe_openrig(run_process=run_process, which=which, ledger=ledger, live_rig_ids=live_rig_ids)
    except Exception:  # noqa: BLE001 - a status probe must not fail the endpoint
        logger.warning("OpenRig status probe failed", exc_info=True)
        openrig = {"daemon": "unknown", "ledger": {"owners": 0, "rigIds": []}}
    if openrig is None:
        backends.append({"name": "openrig", "available": False, "detail": "rig executable not found"})
    else:
        ledger_summary = openrig["ledger"]
        backends.append({
            "name": "openrig",
            "available": openrig["daemon"] == "up",
            "detail": (
                f"daemon {openrig['daemon']}; {ledger_summary['owners']} owner(s) "
                f"hold {len(ledger_summary['rigIds'])} rig(s) in the ledger"
            ),
        })
    return backends, openrig


def build_execution_snapshot(registry=None, probe=None):
    """The D-009 GET /execution body: backend status, live resources, OpenRig daemon and ledger."""
    registry = registry or default_execution_registry
    if probe is None:
        live = set()
        backends, openrig = probe_backends(live_rig_ids=live)
        if openrig is not None and openrig.get("daemon") == "up":
            registry.prune_restored_rigs(live)
    else:
        backends, openrig = probe()
    # Epoch seconds on the same clock as event rawTs, read before the resources: every event the
    # snapshot does not yet reflect has a later rawTs, so clients can drop anything at or before it.
    taken_at = time.time()
    return {
        "backends": backends, "resources": registry.resources(), "openrig": openrig, "takenAt": taken_at,
    }
