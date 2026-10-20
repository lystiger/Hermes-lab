# Hermes M12 verifier

Do not change source. Check the change on this branch:
1. Diff against the base. Confirm an environment-blocked verdict ends the job with a reason and creates no fix phase, and a repairable defect still creates one.
2. Run the pytest suite with the venv: /home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests -q --ignore=tests/smoke -p no:cacheprovider. If a test fails with a permission error on listening sockets (EPERM), rerun that file alone and record it as "NOT RUN: sandbox".
3. Confirm GET /jobs and GET /jobs/{id} response shapes are unchanged except the reason text.

Verdict rule: PASS when the diff is clean and the suite passes except sandbox-blocked tests. FAIL only for a defect shown in the code or a failing test. Environment blocks are not defects.

Write HANDOFF_CODEX.md with PASS or FAIL, the evidence, what was NOT RUN and why. No commits. Leave the file untracked.
