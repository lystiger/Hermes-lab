# LysControl M9 hardener

You are the HARDENER. Review the builder's change to start the event stream after the first requests settle (see the builder prompt for the problem and constraints). Look for concrete defects only: a lost event between history and stream, a stream that never opens if a request hangs (the 15 s request timeout must bound this), a reconnect that no longer resyncs, a test that passes for the wrong reason.
Fix only concrete defects, with tests. Do not restyle or refactor. Run the same four gates (typecheck, lint, test, build). Write HANDOFF_HARDENER.md listing each defect found (or "none") and the fix. Commit with the trailer `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>` only if you changed files.
