# LysControl M10 hardener (review)

You are the HARDENER for the compact-UI change (builder commit e3f2f5f, base of this sprint). Look for concrete defects: long values that still overlap or clip without a tooltip, lost information, and tests that pass for the wrong reason.

A previous hardener proposed two things, saved in the Hermes-lab repo (read them with `cat`, not in this worktree):
- prompts/salvage/m10-inspector-tooltips.patch: the full phase path in the phase tooltip, and the duration and durability shown in the event kind tooltip (those columns are hidden below 1280 px), with a test.

Steps:
1. Check each proposed change against the code. Apply the ones that fix a real defect (`git apply` the patch, or reimplement cleanly). Skip the rest and say why.
2. Run the four gates: npm run typecheck, npm run lint, npm run test -- --run, npm run build.
3. Write HANDOFF_HARDENER.md: each defect, the decision, the gate results.
4. Commit only if files changed, with the trailer `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>`.

Do not use git stash, git checkout on existing files, or git reset. Do not restyle.
