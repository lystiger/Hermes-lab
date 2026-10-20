# LysControl persona-core verifier

Do not change source. Check the change on this branch:
1. Diff against the base. Confirm the listed picture files are deleted, no text files are deleted, and no image path remains in src (run `grep -rn "\.webp\|\.png\|/portrait/\|/agents/" src` and report the output).
2. Run the four gates and report exit codes and test counts.
3. Browser checks (dev server, Chromium) are NOT required. If you try and the sandbox blocks it, record "NOT RUN: sandbox" and do not count it as a failure.

Verdict rule: PASS when the diff and the four gates are clean. FAIL only for a defect shown in the code or a failing gate. Environment blocks are not defects.

Write HANDOFF_CODEX.md with PASS or FAIL, the evidence, what was NOT RUN and why. No commits. Leave the file untracked.
