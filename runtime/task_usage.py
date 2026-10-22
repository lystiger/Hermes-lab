"""Token use of one agent run, normalized across agent CLIs, and the per-job record built from it.

Each finished task appends one line to <run_dir>/usage.jsonl, so a job's usage survives a runtime restart
(the capacity registry is in memory). Fields:
- input_tokens: tokens read fresh (for Claude, plain input plus cache writes)
- cached_tokens: tokens read from the prompt cache (Claude re-reads the conversation every turn)
- output_tokens, total_tokens, cost_usd (when the CLI reports it), turns (when reported)
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

USAGE_FILE = "usage.jsonl"
CODEX_TOTAL = re.compile(r"tokens used\s*\n\s*([\d,]+)")


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def task_usage(runtime_meta: Optional[Dict[str, Any]], stdout_text: str = "", stderr_text: str = "") -> Dict[str, Any]:
    """Usage of one agent run from the agent's own report. Unknown values stay 0 or None."""
    usage: Dict[str, Any] = {}
    meta = runtime_meta or {}
    raw = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
    cost = turns = None

    # Claude prints one JSON object with usage, total_cost_usd and num_turns.
    try:
        final = json.loads((stdout_text or "").strip())
    except (ValueError, TypeError):
        final = None
    if isinstance(final, dict):
        raw = raw or (final.get("usage") if isinstance(final.get("usage"), dict) else {})
        cost = final.get("total_cost_usd")
        turns = final.get("num_turns")

    usage["input_tokens"] = _int(raw.get("input_tokens") or raw.get("prompt_tokens")) + _int(raw.get("cache_creation_input_tokens"))
    usage["cached_tokens"] = _int(raw.get("cache_read_input_tokens") or raw.get("cache_read_tokens") or raw.get("cached_tokens"))
    usage["output_tokens"] = _int(raw.get("output_tokens") or raw.get("completion_tokens"))
    usage["total_tokens"] = usage["input_tokens"] + usage["cached_tokens"] + usage["output_tokens"]

    # Codex reports only a total, at the end of stderr.
    if usage["total_tokens"] == 0:
        match = CODEX_TOTAL.search(stderr_text or "")
        if match:
            usage["total_tokens"] = int(match.group(1).replace(",", ""))

    usage["cost_usd"] = float(cost) if isinstance(cost, (int, float)) else None
    usage["turns"] = turns if isinstance(turns, int) else None
    return usage


def append_usage(run_dir: Path, record: Dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / USAGE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def read_job_usage(run_dir: Path) -> Optional[Dict[str, Any]]:
    """Totals and per-task rows for a job, or None when the job recorded no usage file."""
    path = run_dir / USAGE_FILE
    if not path.exists():
        return None
    tasks: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            tasks.append(json.loads(line))
        except ValueError:
            continue
    totals = {k: sum(_int(t.get(k)) for t in tasks) for k in ("input_tokens", "cached_tokens", "output_tokens", "total_tokens")}
    costs = [t["cost_usd"] for t in tasks if isinstance(t.get("cost_usd"), (int, float))]
    return {"tokens": totals, "costUsd": round(sum(costs), 6) if costs else None, "tasks": tasks}
