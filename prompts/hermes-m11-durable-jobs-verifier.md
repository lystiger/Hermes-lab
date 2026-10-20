# Hermes M11 verifier

Do not change source. Independently check the durable job change on this branch:
1. Diff against the base. Confirm writes are atomic, reload covers all persisted jobs, and interrupted jobs become FAILED.
2. Confirm the response shapes of `GET /jobs` and `GET /jobs/{id}` are unchanged (compare with the base).
3. Run the pytest gate with the venv and report the exit code and counts.
Write HANDOFF_CODEX.md with PASS or FAIL, the evidence, and any concern. No commits.
