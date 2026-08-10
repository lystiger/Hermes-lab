# Sprint 04 Verification Handoff

## Verified

- Backend registry and selection precedence.
- Subprocess stdout, stderr, exit, missing-executable, and timeout parity.
- Herdr preflight and distinct protocol/runtime error mappings.
- Opaque workspace, root-pane, and worker-pane JSON ID parsing.
- Adversarial prompt/argv safety across shell metacharacters, substitutions, Unicode, newlines, and large Markdown.
- Exact completion nonce behavior, non-zero propagation, partial logs, targeted timeout interruption, and runner-owned cleanup.
- Existing controller and worker sandbox invariants.

## Runtime status

The real Herdr smoke/dogfood test is skipped unless the test process is inside a Herdr-managed pane with a reachable server. This implementation session had `HERDR_ENV` unset, so the Herdr skill prohibited controlling a live workspace from it.

## Test result

`pytest -q`: **61 passed, 1 skipped** in the isolated repository environment.

The skipped test is the live Herdr shell smoke test described above. One existing Starlette `TestClient` deprecation warning remains and does not affect Sprint 04.
