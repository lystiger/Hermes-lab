"""Read-only usage-limit records written by the LysOmarchy agents plugin."""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


ALARM_AT_PCT = 90
WARN_AT_PCT = 75
STALE_AFTER_SECONDS = 15 * 60
DEFAULT_USAGE_DIRECTORY = Path("~/.local/state/omarchy/agents/usage")


def _parse_time(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _seconds_until(reset: Optional[datetime], now: datetime) -> int:
    if reset is None:
        return 0
    return max(0, int((reset - now).total_seconds()))


def _percent(value: Any) -> float:
    try:
        return min(1.0, max(0.0, float(value))) * 100
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _text(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _future(reset: Optional[datetime], now: datetime) -> Optional[datetime]:
    """A reset time that has already passed is unknown, not a time to show."""
    return reset if reset is not None and reset > now else None


def _status(used: Optional[float]) -> str:
    if used is None:
        return "unknown"
    return "alarm" if used >= ALARM_AT_PCT else "warn" if used >= WARN_AT_PCT else "ok"


def _agent_from_record(record: Dict[str, Any], filename: str, modified: datetime, now: datetime) -> Dict[str, Any]:
    updated = _parse_time(record.get("updatedAt")) or modified
    limits = record.get("limits") if isinstance(record.get("limits"), list) else []
    windows = []
    for item in limits:
        if not isinstance(item, dict):
            continue
        used = _percent(item.get("percent"))
        reset = _future(_parse_time(item.get("resetsAt")), now)
        windows.append({
            "label": _text(item.get("label")),
            "usedRaw": used,
            "usedPct": round(used),
            "leftPct": round(max(0.0, min(100.0, 100.0 - used))),
            "resetsAt": _iso(reset) if reset else None,
            "resetsInSeconds": _seconds_until(reset, now),
        })

    headline = max(windows, key=lambda window: window["usedRaw"], default=None)
    used = headline["usedRaw"] if headline else None
    reset = _parse_time(headline["resetsAt"]) if headline and headline["resetsAt"] else None
    for window in windows:
        del window["usedRaw"]
    raw_balance = record.get("balance") if isinstance(record.get("balance"), dict) else None
    balance = None
    if raw_balance is not None:
        balance = {key: _positive_number(raw_balance.get(key)) for key in ("funded", "remaining", "spent")}
        balance["currency"] = _text(raw_balance.get("currency"))
    if balance and balance["funded"] > 0:
        left = max(0.0, min(100.0, balance["remaining"] / balance["funded"] * 100))
        used = max(used or 0.0, 100.0 - left)
    elif used is not None:
        left = max(0.0, min(100.0, 100.0 - used))
    else:
        # No window and no funded balance: the record says nothing about what is left.
        left = None

    return {
        "id": _text(record.get("id")) or filename,
        "name": _text(record.get("name")) or _text(record.get("id")) or filename,
        "plan": _text(record.get("tierLabel")),
        "ready": record.get("ready") is True,
        "stale": (now - updated).total_seconds() > STALE_AFTER_SECONDS,
        "status": _status(used),
        "usedPct": None if used is None else round(used),
        "leftPct": None if left is None else round(left),
        "resetsAt": _iso(reset) if reset else None,
        "resetsInSeconds": _seconds_until(reset, now),
        "windows": windows,
        "balance": balance,
        "updatedAt": _iso(updated),
        "authHelp": _text(record.get("authHelpText")),
    }


def _positive_number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return number if math.isfinite(number) and number > 0 else 0.0


def load_agent_limits(directory: Any = DEFAULT_USAGE_DIRECTORY, now: Optional[datetime] = None) -> list[Dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    path = Path(directory).expanduser()
    if not path.is_dir():
        return []
    agents = []
    for entry in path.iterdir():
        if entry.name.startswith(".") or not entry.is_file() or entry.suffix.lower() != ".json":
            continue
        try:
            modified = datetime.fromtimestamp(entry.stat().st_mtime, timezone.utc)
        except (OSError, OverflowError, ValueError):
            continue
        try:
            with entry.open(encoding="utf-8") as handle:
                record = json.load(handle)
            if not isinstance(record, dict):
                raise ValueError("record is not an object")
        except (OSError, ValueError, RecursionError):
            record = {"id": entry.stem, "name": entry.stem, "ready": False}
        agents.append(_agent_from_record(record, entry.stem, modified, now))
    return sorted(agents, key=lambda agent: str(agent["id"]))
