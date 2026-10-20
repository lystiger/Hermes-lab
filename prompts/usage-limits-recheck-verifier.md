# Usage limits: recheck verifier

Do not change source. Check the change on this branch:
1. Run the gates listed in the sprint. Run Python with `/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest`: the system Python has no pytest or FastAPI. Run console gates inside `console/` after `npm ci`.
2. Check `/capacity/limits` returns the documented shape, and that the math matches the rules in the builder prompt.
3. Browser checks are not required. If the sandbox blocks a check, record "NOT RUN: sandbox" and do not count it as a failure.

Write HANDOFF_CODEX.md with PASS or FAIL, the evidence, and what was NOT RUN and why. Use your file-write tool, not a shell heredoc or redirect. No commits, and do not modify product files. Leave the file untracked.
