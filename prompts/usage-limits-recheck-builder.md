# Usage limits: recheck builder

The usage feature is already on this base: `runtime/usage_limits.py`, `GET /capacity/limits`, and the Usage page in `console/`. Do not rewrite it.

Your job:
1. Read the backend and frontend code for the usage feature.
2. Check it against these rules:
   - The fullest window decides the headline: `leftPct = 100 − usedPct`, clamped to 0–100.
   - Balance agents use `remaining / funded` when `funded > 0`.
   - Status: `alarm` at 90 or more used, `warn` at 75 or more, otherwise `ok`. No limit data gives `unknown` with null percentages.
   - The page shows what the backend returns and never recomputes it. A null value shows as a dash.
3. Fix only concrete defects, each with a test. Keep the existing tests passing.

Python: run tests with `/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest`. Console work happens inside `console/`.

Write HANDOFF_BUILDER.md with what you checked, what you changed (or "no defects"), and the test results. Use your file-write tool, not a shell heredoc or redirect. Do not run git commands: the controller stages and commits your changes, and it excludes the handoff file.
