# LysControl M9 hardener (review)

You are the HARDENER for the stream-start change (commit 57d8242, base of this sprint). Read the builder's code in src/api/hooks.ts (useEventStream) and src/api/adapters/httpAdapter.ts (waitForIdle).

A previous hardener found one defect: when history is empty there is no cursor, so the stream starts at "now" and any events emitted during the idle wait are lost. Its proposed fix is in prompts/salvage/m9-stream-history-reload.patch (in the Hermes-lab repo, not in this worktree; read it with `cat`). It reloads history after the wait when there is no cursor, and adds a test for it.

Steps:
1. Confirm the defect by reading the code. If it is real, apply the change (`git apply` the patch, or reimplement it cleanly). If it is not real, say why and change nothing.
2. Run the four gates: npm run typecheck, npm run lint, npm run test -- --run, npm run build.
3. Write HANDOFF_HARDENER.md: the defect, the decision, the gate results.
4. Commit only if files changed, with the trailer `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>`.

Do not use git stash, git checkout on existing files, or git reset. Do not change the Agents data model.
