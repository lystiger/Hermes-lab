# LysControl M10 verifier

Do not change product source. Check the compact-UI change on this branch:
1. Diff against the base. Confirm long values are truncated with a `title` or wrapped, not dropped, and that the Overview has fewer words than before.
2. Run the four gates (typecheck, lint, test, build) and report exit codes and test counts.
3. Browser checks (dev server, Chromium, screenshots) are NOT required here. The sandbox blocks listening sockets and Chromium. If you try, record "NOT RUN: sandbox" and do not count it as a failure.

Verdict rule: PASS when the diff and the four gates are clean. Only FAIL for a defect you can show in the code or a failing gate. Environment blocks are not defects.

Write HANDOFF_CODEX.md with PASS or FAIL, the evidence (commands, exit codes, counts), what was NOT RUN and why, and any concern. No commits.
