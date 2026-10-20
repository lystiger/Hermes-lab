"""Read-only usage-limit records written by the LysOmarchy agents plugin."""

import json
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
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _seconds_until(reset: Optional[datetime], now: datetime) -> int:
    if reset is None:
        return 0
    return max(0, int((reset - now).total_seconds()))


def _percent(value: Any) -> float:
    try:
        return min(1.0, max(0.0, float(value))) * 100
    except (TypeError, ValueError):
        return 0.0


def _agent_from_record(record: Dict[str, Any], filename: str, modified: datetime, now: datetime) -> Dict[str, Any]:
    updated = _parse_time(record.get("updatedAt")) or modified
    limits = record.get("limits") if isinstance(record.get("limits"), list) else []
    windows = []
    for item in limits:
        if not isinstance(item, dict):
            continue
        used = _percent(item.get("percent"))
        reset = _parse_time(item.get("resetsAt"))
        windows.append({
            "label": item.get("label", ""),
            "usedPct": round(used),
            "leftPct": round(max(0.0, min(100.0, 100.0 - used))),
            "resetsAt": _iso(reset) if reset else None,
            "resetsInSeconds": _seconds_until(reset, now),
        })

    headline = max(windows, key=lambda window: window["usedPct"], default=None)
    used = float(headline["usedPct"]) if headline else 0.0
    reset = _parse_time(headline["resetsAt"]) if headline and headline["resetsAt"] else None
    balance = record.get("balance") if isinstance(record.get("balance"), dict) else None
    if balance and _positive_number(balance.get("funded")) > 0:
        left = max(0.0, min(100.0, _positive_number(balance.get("remaining")) / _positive_number(balance["funded"]) * 100))
    else:
        left = max(0.0, min(100.0, 100.0 - used))

    return {
        "id": record.get("id") or filename,
        "name": record.get("name") or record.get("id") or filename,
        "plan": record.get("tierLabel", ""),
        "ready": bool(record.get("ready", False)),
        "stale": (now - updated).total_seconds() > STALE_AFTER_SECONDS,
        "status": "alarm" if used >= ALARM_AT_PCT else "warn" if used >= WARN_AT_PCT else "ok",
        "usedPct": round(used),
        "leftPct": round(left),
        "resetsAt": _iso(reset) if reset else None,
        "resetsInSeconds": _seconds_until(reset, now),
        "windows": windows,
        "balance": balance,
        "updatedAt": _iso(updated),
        "authHelp": record.get("authHelpText", ""),
    }


def _positive_number(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


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
        modified = datetime.fromtimestamp(entry.stat().st_mtime, timezone.utc)
        try:
            with entry.open(encoding="utf-8") as handle:
                record = json.load(handle)
            if not isinstance(record, dict):
                raise ValueError("record is not an object")
        except (OSError, ValueError, json.JSONDecodeError):
            record = {"id": entry.stem, "name": entry.stem, "ready": False}
        agents.append(_agent_from_record(record, entry.stem, modified, now))
    return sorted(agents, key=lambda agent: str(agent["id"]))
