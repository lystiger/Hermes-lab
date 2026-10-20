# LysControl: remove character art from the core

You are the BUILDER. Repository: LysControl (React 19, Vite, TypeScript, Vitest). Work in this worktree on the sprint branch.

## Goal
The core console ships without character art. Character art moves to a separate theme repository, LysStack-persona, that will be loaded later. This sprint only removes the art from the core and makes the console render correctly without it.

## Steps
1. Delete these tracked picture files with `git rm`:
   - public/agents/*.webp (seven files: claude, codex, gemini, hermes, and the three -card files)
   - design-reference/cards/*.png (claude, codex, gemini)
   - design-reference/screenshots/*.png (nine files)
   Do not delete any text file, including design-reference/*.html and the .js files there.
2. Remove the image references from source. In src/theme/agentArt.ts, `agentArt()` returns undefined for every id and `HERMES_ART` is undefined; remove the art paths entirely. Update src/api/actors.ts, src/api/adapters/httpAdapter.ts and src/api/mock/agents.ts so that avatar and card URLs are undefined (no `/portrait/` or `/agents/` paths remain). The existing fallback (initials and a sigil, already tested) must show in their place.
3. Make every component that reads art handle undefined: AgentPortrait, AgentDossier, EmptyState art, MissionBoard and ActiveExecutionCard (Hermes art), events and index empty states. They must render the fallback, not a broken image.
4. Update tests that assert image paths to assert the fallback instead. Do not delete a test to make it pass; change its expectation and say why in the handoff.
5. `grep -rn "\.webp\|\.png\|/portrait/\|/agents/" src` must return nothing except comments.

## Constraints
- Do not change layout, copy or behaviour beyond the fallback.
- Do not add any image file.
- Do not touch .gitignore.

## Gates (all must exit 0)
npm run typecheck, npm run lint, npm run test -- --run, npm run build.

## Handoff
Write HANDOFF_BUILDER.md: the files deleted, the files changed, the test expectations you changed and why, gate results. Commit with `chore: remove character art from the core (moves to LysStack-persona)`, ending with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Leave HANDOFF_BUILDER.md untracked.
