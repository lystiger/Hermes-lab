# LysControl M9 hardener review

Base reviewed: `57d8242`.

## Defect and decision

Confirmed in `useEventStream` and `HttpHermesApi.waitForIdle`: when initial history is empty, `initialCursor` is undefined. Outstanding HTTP requests can delay stream startup while events are emitted. With no cursor (and no prior adapter event ID), SSE starts at now and skips those events.

Applied `/home/lystiger/Projects/Hermes-lab/prompts/salvage/m9-stream-history-reload.patch`, then formatted the extracted history loader. After the idle barrier, reload history if there is no cursor and the effect is still subscribed and not aborted. This reuses historical event ingestion, execution replay, and newest-cursor selection. No adapter or Agents data-model changes.

Regression: hold an agents request open, return empty initial history, return `during-wait` from the second history read, release the pending request, and assert two history reads, recovered event in the console store, and subscription cursor `during-wait`. Reset console events before each startup test to isolate store assertions.

## Gate results

- `npm run typecheck`: PASS, exit 0.
- `npm run lint`: PASS, exit 0, no diagnostics.
- `npm run test -- --run`: PASS, exit 0; 36 test files, 285 tests.
- `npm run build`: PASS, exit 0; 1895 modules transformed.

During test development, the added store assertion first used nonexistent `events` (`TypeError: undefined is not iterable (cannot read property Symbol(Symbol.iterator))`), then failed against `allEvents` retained by earlier tests (`AssertionError: expected [ { id: 'next-event', …(2) }, …(4) ] to deep equally contain { id: 'during-wait', rawTs: 60, …(1) }`). Corrected the property and isolated test state; final full suite passes.

Existing startup tests also cover pending request success/failure, newest cursor selection, immediate idle startup, drop/resync, unmount cancellation, and requests starting before the idle waiter resumes.

## Limits

The fix recovers events visible in the post-wait history read. If that read fails or is still empty, startup remains cursorless; it does not provide an atomic history-to-stream boundary or change backend replay semantics.

## Commit blocked by workspace permissions

Attempted to stage these three files and commit with the required trailer `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>`. Both Git operations failed because this worktree's Git metadata is outside the writable roots:

```text
fatal: Unable to create '/home/lystiger/Projects/LysControl/.git/worktrees/hardener1/index.lock': Read-only file system
```

Changes remain unstaged. No commit was created.
