# Usage limits: verifier

Do not change source. Check the change on this branch:
1. Run the verification gates listed in the sprint (pytest, console install, typecheck, console tests).
2. Check that `/capacity/limits` returns the documented shape, and that the math matches the rules in the backend prompt: fullest window, `left = 100 − used`, thresholds 75 and 90.
3. Browser checks are not required. If the sandbox blocks a check, record "NOT RUN: sandbox" and do not count it as a failure.

Write HANDOFF_CODEX.md with PASS or FAIL, the evidence, and what was NOT RUN and why. Use your file-write tool, not a shell heredoc or redirect. No commits, and do not modify product files. Leave the file untracked.
