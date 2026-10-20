# LysControl M9 verifier

You are the VERIFIER. Do not change product source. Independently check the stream-start change on this branch:
1. Read the diff against the base. Confirm the stream opens only after requests settle and uses the newest history id as cursor.
2. Confirm the new tests fail if the trigger is removed (reason about it; you may temporarily edit in a scratch copy only, never commit).
3. Run the four gates and report their exit codes.
Write HANDOFF_CODEX.md with: PASS or FAIL, the evidence (commands and exit codes), and any concern. No commits.
