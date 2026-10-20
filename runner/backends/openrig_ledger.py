"""Crash-safe ownership ledger for OpenRig rigs that Hermes launched.

The OpenRig backend records every rigId it launches here before relying on it, and
drops the rigId only after `rig down` confirms the release. If the Hermes process
dies first, the entry survives. The next backend preflight releases the entries
whose owning process is gone.

Location: a per-user state directory, not the run directory. A crash can leave the
next run with a new run directory, so reconciliation has to see every run.
Resolution order: `HERMES_OPENRIG_LEDGER_DIR`, then `$XDG_STATE_HOME/hermes/openrig-ledger`,
then `~/.local/state/hermes/openrig-ledger`.

Layout: one JSON file per owning process, `<host>-<pid>-<start>.json`, holding
`{"host", "pid", "started", "rigIds"}`. Each process writes only its own file. Pids mean
nothing on another machine, so an entry from another host is never judged dead here.

Ownership is by exact rigId only. Nothing here matches rigs by name.
"""

import contextlib
import json
import logging
import os
import re
import socket
import tempfile
import threading
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows has no fcntl; msvcrt locks a byte range instead.
    fcntl = None
    import msvcrt


def _lock_file(handle):
    if fcntl is not None:
        fcntl.flock(handle, fcntl.LOCK_EX)
        return
    handle.seek(0)
    while True:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            return
        except OSError:
            time.sleep(0.01)


def _unlock_file(handle):
    if fcntl is not None:
        fcntl.flock(handle, fcntl.LOCK_UN)
        return
    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

LEDGER_DIR_ENV = "HERMES_OPENRIG_LEDGER_DIR"
logger = logging.getLogger("hermes.runtime.openrig_ledger")
# One lock for the process: every backend instance shares the same ledger files.
# Cross-process safety comes from flock on the directory's .lock file (see _locked).
_LOCK = threading.Lock()
# OpenRig rigIds are ULIDs. `rig down` also resolves rig names, so a ledger entry that is
# not a ULID (for example "kernel") must never be read back as something to release.
_RIG_ID = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}")
# Hermes rig names: hermes-<slug>-<8 random hex>. Unique per launch, so a pending launch can be
# recognised by name; teardown still happens only by the rigId found under that name.
_RIG_NAME = re.compile(r"hermes-[a-z0-9-]{1,40}-[0-9a-f]{8}")
PENDING_SUFFIX = ".pending"
PENDING_STATES = ("launching", "abandoned")


def default_ledger_dir():
    override = os.environ.get(LEDGER_DIR_ENV)
    if override:
        return Path(override)
    state_home = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(state_home) / "hermes" / "openrig-ledger"


def _proc_stat(pid):
    """Return (state, start_token) from /proc, or None when the process cannot be read."""
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        # The comm field is parenthesised and may contain spaces; fields resume after the last ')'.
        # After it, index 0 is field 3 (state) and index 19 is field 22 (starttime, clock ticks).
        fields = text[text.rindex(")") + 2:].split()
        return fields[0], fields[19]
    except (OSError, ValueError, IndexError):
        return None


def process_identity():
    """(pid, start_token) of this process. The start token defeats pid reuse."""
    pid = os.getpid()
    stat = _proc_stat(pid)
    return pid, stat[1] if stat else None


def _host():
    return socket.gethostname()


def owner_alive(pid, started):
    """False only when the owner is provably gone: no such pid, a zombie, or a reused pid.

    When the process cannot be inspected it is treated as alive, so a guess never releases a rig.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass  # exists, owned by another user
    stat = _proc_stat(pid)
    if stat is None:
        return True
    state, token = stat
    if state in ("Z", "X"):
        return False
    return started is None or token == started


def _read(path):
    """Return (host, pid, started, rig_ids). Raises ValueError for a file that is not a valid ledger."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} is not a ledger object")
    host, pid = data.get("host"), data.get("pid")
    started, rig_ids = data.get("started"), data.get("rigIds")
    if (
        not isinstance(host, str) or not host
        or not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0
        or (started is not None and not isinstance(started, str))
        or not isinstance(rig_ids, list)
        or not all(isinstance(rig_id, str) and _RIG_ID.fullmatch(rig_id) for rig_id in rig_ids)
    ):
        raise ValueError(f"{path.name} is malformed")
    return host, pid, started, list(rig_ids)


def _write(path, host, pid, started, rig_ids):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"host": host, "pid": pid, "started": started, "rigIds": rig_ids}, indent=2,
    ) + "\n"
    # Write-then-replace so a crash mid-write never leaves a truncated ledger.
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


class StaleOwner:
    """Ledger entries whose owning process on this host is gone."""

    def __init__(self, path, pid, rig_ids):
        self.path = path
        self.pid = pid
        self.rig_ids = tuple(rig_ids)


class OwnershipLedger:
    def __init__(self, directory=None, identity=None):
        self.directory = Path(directory) if directory is not None else default_ledger_dir()
        # Injectable so tests can act as a different (for example crashed) owner.
        self._identity = identity or process_identity

    def record(self, rig_id):
        """Persist ownership of `rig_id`. Raises OSError or ValueError if it cannot be written."""
        if not isinstance(rig_id, str) or not _RIG_ID.fullmatch(rig_id):
            raise ValueError(f"{rig_id!r} is not an OpenRig rigId")
        host, (pid, started) = _host(), self._identity()
        path = self.directory / f"{host}-{pid}-{started or 'unknown'}.json"
        with self._locked():
            rig_ids = _read(path)[3] if path.exists() else []
            if rig_id not in rig_ids:
                rig_ids.append(rig_id)
            _write(path, host, pid, started, rig_ids)

    def forget(self, rig_id):
        """Drop `rig_id` from every ledger file. A file left empty is deleted.

        Raises OSError if a file cannot be rewritten. The caller decides how to treat that.
        """
        with self._locked():
            for path in self._files():
                try:
                    host, pid, started, rig_ids = _read(path)
                except (OSError, ValueError) as exc:
                    logger.warning("Skipping unreadable OpenRig ledger file %s: %s", path, exc)
                    continue
                if rig_id not in rig_ids:
                    continue
                rest = [r for r in rig_ids if r != rig_id]
                if rest:
                    _write(path, host, pid, started, rest)
                else:
                    path.unlink(missing_ok=True)

    def stale_owners(self):
        """Entries whose owning process on this host is provably gone.

        Live owners and other hosts' entries are skipped. Unreadable files are logged and
        kept, never released. A dead owner with nothing left to release has its file removed.
        """
        stale = []
        with self._locked():
            for path in self._files():
                try:
                    host, pid, started, rig_ids = _read(path)
                except (OSError, ValueError) as exc:
                    logger.warning("Skipping unreadable OpenRig ledger file %s: %s", path, exc)
                    continue
                if host != _host() or owner_alive(pid, started):
                    continue
                if not rig_ids:
                    path.unlink(missing_ok=True)
                    continue
                stale.append(StaleOwner(path, pid, rig_ids))
        return stale

    # -- pending launches ------------------------------------------------------
    # `rig up` can finish creating a rig after Hermes stopped waiting (cancel, lost response). The
    # launch is recorded by its unique name before `rig up` runs and cleared once its rigId is tracked.
    # If it was abandoned (or its owner died mid-launch), any later preflight that finds a rig with that
    # exact name adopts its rigId and releases it.

    def _pending_path(self):
        host, (pid, started) = _host(), self._identity()
        return self.directory / f"{host}-{pid}-{started or 'unknown'}{PENDING_SUFFIX}"

    def _read_pending(self, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data.get("pending") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            raise ValueError(f"{path.name} is malformed")
        valid = [
            e for e in entries
            if isinstance(e, dict) and isinstance(e.get("name"), str) and _RIG_NAME.fullmatch(e["name"])
            and e.get("state") in PENDING_STATES and isinstance(e.get("at"), (int, float))
        ]
        return data, valid

    def _write_pending(self, path, data, entries):
        if not entries:
            path.unlink(missing_ok=True)
            return
        payload = dict(data, pending=entries)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def record_pending(self, rig_name, now):
        """Record a launch about to start. Raises OSError/ValueError if it cannot be written."""
        if not isinstance(rig_name, str) or not _RIG_NAME.fullmatch(rig_name):
            raise ValueError(f"{rig_name!r} is not a Hermes rig name")
        host, (pid, started) = _host(), self._identity()
        path = self._pending_path()
        with self._locked():
            data, entries = (self._read_pending(path) if path.exists()
                             else ({"host": host, "pid": pid, "started": started}, []))
            entries = [e for e in entries if e["name"] != rig_name]
            entries.append({"name": rig_name, "state": "launching", "at": now})
            self._write_pending(path, data, entries)

    def _update_pending(self, rig_name, change):
        with self._locked():
            for path in sorted(self.directory.glob(f"*{PENDING_SUFFIX}")) if self.directory.is_dir() else []:
                try:
                    data, entries = self._read_pending(path)
                except (OSError, ValueError):
                    continue
                updated = change(entries)
                if updated != entries:
                    self._write_pending(path, data, updated)

    def clear_pending(self, rig_name):
        """The launch's rigId is tracked (or released): stop watching its name."""
        self._update_pending(rig_name, lambda entries: [e for e in entries if e["name"] != rig_name])

    def abandon_pending(self, rig_name):
        """The launch ended without a tracked rigId: a later preflight may still find and release it."""
        self._update_pending(rig_name, lambda entries: [
            dict(e, state="abandoned") if e["name"] == rig_name else e for e in entries
        ])

    def pending_to_reconcile(self, now, max_age):
        """Names of launches nobody is waiting for: abandoned ones, or ones whose owner died.

        A launch still in progress in a live process is never returned. Entries older than
        `max_age` seconds are dropped with a warning (a rig that never appeared is not waited on forever).
        """
        names = []
        with self._locked():
            for path in sorted(self.directory.glob(f"*{PENDING_SUFFIX}")):
                try:
                    data, entries = self._read_pending(path)
                except (OSError, ValueError) as exc:
                    logger.warning("Skipping unreadable OpenRig pending file %s: %s", path, exc)
                    continue
                if data.get("host") != _host():
                    continue
                owner_dead = not owner_alive(data.get("pid") or 0, data.get("started")) if data.get("pid") else True
                kept = []
                for entry in entries:
                    if now - entry["at"] > max_age:
                        logger.warning("Gave up on OpenRig launch %s: no rig appeared within %ss", entry["name"], max_age)
                        continue
                    kept.append(entry)
                    if entry["state"] == "abandoned" or owner_dead:
                        names.append(entry["name"])
                if kept != entries:
                    self._write_pending(path, data, kept)
        return names

    def summary(self):
        """Read-only view: how many owners hold rigs, and which rigIds they are.

        Unlike stale_owners(), this takes no lock, creates no directory and deletes nothing.
        Writes are atomic replacements, so a plain read never sees a partial file.
        """
        owners = 0
        rig_ids = []
        for path in self._files():
            try:
                _, _, _, ids = _read(path)
            except (OSError, ValueError):
                continue
            if ids:
                owners += 1
                rig_ids.extend(ids)
        return {"owners": owners, "rigIds": rig_ids}

    @contextlib.contextmanager
    def _locked(self):
        """Serialize ledger reads and rewrites across threads and Hermes processes."""
        with _LOCK:
            self.directory.mkdir(parents=True, exist_ok=True)
            with open(self.directory / ".lock", "a+") as handle:
                _lock_file(handle)
                try:
                    yield
                finally:
                    _unlock_file(handle)

    def _files(self):
        if not self.directory.is_dir():
            return []
        return sorted(self.directory.glob("*.json"))
