# Usage limits: backend

You are the BUILDER. Repository: this Hermes runtime (Python). Work in this worktree on the sprint branch. Do not touch `console/`.

## Goal
Show how much of each agent's allowance is left, using the same math as the LysOmarchy agents plugin. The plugin writes one JSON record per agent to `~/.local/state/omarchy/agents/usage/<id>.json`. Hermes reads those records and serves the numbers.

## Input records (read-only)
- Skip dotfiles and files that are not valid JSON. A bad record becomes an agent with `ready: false`, never an error for the whole response.
- Fields you use: `id`, `name`, `ready`, `tierLabel`, `updatedAt` (ISO 8601, may be missing), `authHelpText`, `limits` (list of `{label, title?, percent, resetsAt}`; `percent` is 0–1 used; `resetsAt` ISO 8601, `Z` or `+00:00`), and optional `balance` (`{remaining, funded, currency}`).
- If `updatedAt` is missing, use the file's modification time.

## Math (must match the plugin)
- `usedPct` = max `percent` across `limits` × 100. The fullest window decides the headline.
- `leftPct` = 100 − `usedPct`, clamped to 0–100.
- Balance agents (when `balance.funded > 0`): `leftPct` = remaining / funded × 100. Use this instead of limits when present.
- `status`: `alarm` when used ≥ 90, `warn` when used ≥ 75, otherwise `ok`. Use the constants `ALARM_AT_PCT = 90` and `WARN_AT_PCT = 75`.
- `resetsAt`: the reset time of the headline (fullest) window. `resetsInSeconds` = seconds from now, floored at 0.
- `stale`: true when the record is older than 15 minutes.
- Round percentages to whole numbers in the response.

## Endpoint
Add `GET /capacity/limits` in `main.py`, next to `/capacity/telemetry`. It returns:

```
{"timestamp": "...", "agents": [
  {"id": "claude", "name": "Claude", "plan": "Max 20x", "ready": true, "stale": false,
   "status": "ok", "usedPct": 14, "leftPct": 86,
   "resetsAt": "...", "resetsInSeconds": 7200,
   "windows": [{"label": "Session (5-hour)", "usedPct": 14, "leftPct": 86, "resetsAt": "...", "resetsInSeconds": 7200}],
   "balance": null, "updatedAt": "...", "authHelp": ""}
]}
```

Agents are sorted by id. Do not include prompts, tokens, file paths, or model usage. Keep it read-only.

## Code
- `runtime/usage_limits.py`: the pure functions (`load_agent_limits(directory, now)` and helpers). The directory defaults to `~/.local/state/omarchy/agents/usage`, but the function takes the directory as an argument so tests can use a temp directory.
- `main.py`: the thin route that calls the function with the default directory.
- Standard library only.

## Tests (`tests/test_usage_limits.py`)
- Fullest window sets `usedPct`, `leftPct` and the reset time.
- Thresholds: 74 → ok, 75 → warn, 89 → warn, 90 → alarm.
- Balance: `remaining/funded` drives `leftPct` when `funded > 0`.
- Missing `updatedAt` falls back to the file mtime; an old record is `stale`.
- A corrupt JSON file, and a dotfile, are skipped or reported as not ready without failing the rest.
- `GET /capacity/limits` returns the shape above (use FastAPI's TestClient with a patched directory).

## Constraints
- Do not change the `/capacity/telemetry` response.
- Do not add dependencies.

## Gates
`/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests -q --ignore=tests/smoke -p no:cacheprovider` exits 0.

## Handoff
Write HANDOFF_BUILDER.md with the files changed, the test results, and anything you are unsure about. Use your file-write tool, not a shell heredoc or redirect. Do not run git commands: the controller stages and commits your changes, and it excludes the handoff file.
