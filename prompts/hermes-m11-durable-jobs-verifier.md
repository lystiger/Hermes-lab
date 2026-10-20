# Hermes M11 verifier

Do not change source. Check the durable job change on this branch:
1. Diff against the base. Confirm writes are atomic, reload covers all persisted jobs, and interrupted jobs become FAILED.
2. Confirm the response shapes of `GET /jobs` and `GET /jobs/{id}` are unchanged (compare with the base).
3. Run the pytest suite with the venv: /home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests -q --ignore=tests/smoke -p no:cacheprovider . It takes about one minute. If a test fails with a permission error on listening sockets (EPERM), rerun that test file alone and record it as "NOT RUN: sandbox". Do not count it as a failure.

Verdict rule: PASS when the diff is clean and the suite passes except sandbox-blocked tests. FAIL only for a defect you can show in the code or a failing test. Environment blocks are not defects.

Write HANDOFF_CODEX.md with PASS or FAIL, the evidence, what was NOT RUN and why, and any concern. No commits.
