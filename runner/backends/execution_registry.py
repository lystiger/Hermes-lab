"""In-process view of live execution resources, built from the D-009 event stream.

The registry holds what this process has seen. `build_execution_snapshot()` adds read-only
backend status, including the OpenRig ledger, which covers rigs left by earlier processes.
Nothing here runs a mutating command.
"""

import logging
import shutil
import threading
import time
from datetime import datetime, timezone

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


class ExecutionRegistry:
    """Thread-safe. Events arrive from backend worker threads and timer threads."""

    def __init__(self):
        self._lock = threading.Lock()
        self._resources = {}

    def apply(self, event):
        metadata = event.metadata
        resource = metadata.get("resource")
        if not isinstance(resource, dict):
            return
        key = (metadata.get("backend"), resource.get("kind"), resource.get("id"))
        with self._lock:
            if event.kind == events.RESOURCE_RELEASED:
                self._resources.pop(key, None)
                return
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

    def resources(self):
        with self._lock:
            rows = [dict(row, details=dict(row["details"])) for row in self._resources.values()]
        return sorted(rows, key=lambda row: row["since"] or "")


default_execution_registry = ExecutionRegistry()


def probe_backends(*, which=None, run_process=None, ledger=None):
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
        openrig = describe_openrig(run_process=run_process, which=which, ledger=ledger)
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
    backends, openrig = (probe or probe_backends)()
    # Epoch seconds on the same clock as event rawTs, read before the resources: every event the
    # snapshot does not yet reflect has a later rawTs, so clients can drop anything at or before it.
    taken_at = time.time()
    return {
        "backends": backends, "resources": registry.resources(), "openrig": openrig, "takenAt": taken_at,
    }
