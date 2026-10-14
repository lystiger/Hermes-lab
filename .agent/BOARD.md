# Board — Step 2: Hermes execution-backend readiness

Decision: D-001 (PATH A). Baseline 7d66c65, 366 passed / 6 skipped.
Named worker team was not running; per human choice Opus implemented directly, Codex (pane w1:p2) reviewed once.

| Item | Files | Status |
|---|---|---|
| Per-task backend cleanup in finally | runtime/hermes_adapter.py | DONE |
| Catch SprintRunnerError under both import paths | runtime/hermes_adapter.py | DONE |
| Pass scalar runtime_metadata + backend name into task result | runtime/hermes_adapter.py | DONE (Codex P2) |
| Contract/registry/runtime tests | tests/test_backend_contract.py | DONE (13 tests) |
| Contract doc + future sessionful backend responsibilities | runner/backends/README.md | DONE (Codex P2/P3 wording) |
| Codex review | — | DONE: 2×P2, 1×P3, all fixed; no second review (no design change) |

Final: full suite 379 passed / 6 skipped; compileall runner runtime OK.
