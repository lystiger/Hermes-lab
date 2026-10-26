# Elysia history audit

Status: tool implemented and unit-tested. Real case selection and counts are **pending review** in this step and are not recorded here.

This document describes `tools/elysia_history_audit.py`, an offline, read-only, stdlib-only audit of Hermes job history. It groups job runs into *run families* and proposes a family-level development / held-out split.

Baseline Elysia is advisory QC/PM. Claude feedback is separate: it is not an input to this audit and is not recorded by it.

## Scope and limits

- The audit records file names, sizes, SHA-256 digests, stable identifiers, timestamps, status values and evidence flags.
- It never records observations, error text, blocked-reason text, prompts or transcripts. Those are out of scope by design.
- Metadata alone does not prove case quality. A run can be well-formed, definitive and held out and still be a poor decision case. Case quality needs review of the content, which this tool does not read.
- The later **redaction-reviewed extraction step** creates the real decision cases from the audited families. Until that step and its review happen, no case is selected and no case count is claimed.

## Inventory evidence fields

Each run record in `manifest.json` contains:

| Field | Meaning |
| --- | --- |
| `id` | Job id from `job.json`, or null if unreadable. |
| `sprintId` | Sprint id from `job.json`. |
| `branch_sha256` | SHA-256 of the branch name. The branch name itself is not stored. |
| `status` | Job status, upper-cased. Null if absent. |
| `createdAt`, `completedAt` | Timestamps from `job.json`. |
| `family_id` | Family the run belongs to (see grouping rules). |
| `flags.executing`, `flags.simulated` | See status and flag definitions. |
| `evidence.*` | Presence booleans for the files listed below. |
| `job_json` | Filename, size and SHA-256 of `job.json`. |
| `artifact_files` | For each regular file in the run folder: relative filename, size and SHA-256. |
| `reasons` | Reason codes that explain why the run is not definitive (see below). |

Evidence flags:

- `has_run_summary` (`run_summary.json`)
- `has_artifacts_json` (`artifacts.json`)
- `has_finalize_json` (`finalize.json`)
- `has_runner_log` (`runner.log`)
- `has_messages` (`messages.jsonl`)
- `has_handoffs` (any file under `handoffs/`)
- `has_verification` (`job.json` has a non-null `verification`)
- `has_phases` (`job.json` has a non-empty `phases`)

Scan rules:

- A run is a folder containing `job.json`. Nested folders that contain their own `job.json` are treated as separate runs and are not walked as part of the parent.
- Symlinks are never followed. A symlinked `job.json` is counted in `skipped_symlink_job_files` and not recorded.
- `job.json` larger than 50 MiB is not parsed (reason `job_json_too_large`). `job.json` that is unreadable, invalid JSON or not an object is not parsed (reason `job_json_unreadable`).

## Status and flag definitions

- **Terminal statuses:** `COMPLETED`, `BLOCKED`, `FAILED`, `CANCELLED`.
- **`flags.executing` = true** when the status is not terminal, or `completedAt` is missing. Executing runs are never definitive.
- **`flags.simulated` = true** when any of `dry_run`, `dryRun`, `simulated` or `actor_dry_run` is `true` on the job, on its `metadata`, or on any task. Simulated runs are never definitive.
- **Family `status`:**
  - `definitive`: no reason codes on any member.
  - `needs_review`: at least one reason code. These families are excluded from the split.

## Run-family grouping rules

Grouping is deliberately conservative. A family is merged only on strong evidence. Anything ambiguous is flagged, not guessed.

1. **Identity.** Runs with a missing id are `missing_id`. Runs that share an id with another run are `duplicate_id`. Neither enters grouping; each stands alone as a `needs_review` family.
2. **Retry link.** A run whose `retryHistory` is non-empty is linked to another run only when that other run's id appears as a string in its `retryHistory` *and*:
   - the run-id prefix (the id with all-digit segments removed) matches, *and*
   - the task graph matches (sorted phase and task ids and roles).
   Only then are the two runs merged into one family.
3. **Mismatch.** If the history names another run but the prefix or task graph differs, both runs get `retry_link_mismatch` and are not merged.
4. **Unresolved.** A run with a non-empty `retryHistory` that names no other run gets `retry_link_unresolved`.
5. **Unlinked match.** Runs with the same prefix and task graph that were *not* merged by a retry link are flagged `unlinked_prefix_graph_match`. They may be retries the history does not show, so they are not merged automatically.
6. **Family id.** A grouped family's id is the SHA-256 of its sorted member ids. A standalone (unusable) run's id is the SHA-256 of its root key and `job.json` digest.

Reason codes:

- `job_json_too_large`, `job_json_unreadable`, `missing_id`, `duplicate_id`
- `executing_run`, `simulated_run`, `incomplete_record` (missing `sprintId`, `status` or `createdAt`), `empty_task_graph`
- `retry_link_unresolved`, `retry_link_mismatch`, `unlinked_prefix_graph_match`

### What `needs_review` means

`needs_review` means the tool could not establish a clean, unambiguous family for the run or runs. It does not mean the run is bad. It means the run is excluded from the development and held-out sets, and a person should decide whether it is usable. Excluded families are listed in `split.json` under `excluded_needs_review`.

## Uncertainty and its limits

- **Retry history can be incomplete.** A true retry the history does not name is not linked. Such runs surface only as `unlinked_prefix_graph_match` when they share prefix and graph with another run, and a retry with a different graph is not detected at all.
- **Prefix matching is heuristic.** It strips all-digit segments from the id. Two unrelated jobs with the same non-numeric prefix and identical task graphs would be flagged, not separated.
- **Digests show identity, not meaning.** SHA-256 of files proves a file did not change between scans. It says nothing about the file's content quality.
- **Evidence flags are presence checks.** A present `runner.log` may be empty or truncated. The flags do not check content.
- **Family ids change with membership.** Adding or removing a member changes the sorted-id digest, which can move a family to another split. Splits are stable only while the input set is stable.
- **Scan is point-in-time.** Runs added, changed or removed between scans change the result.
- **Dry-run detection depends on the flags being set.** A simulated run that does not carry one of the four keys is treated as real.

## Proposed family-level dev / held-out split

- Only `definitive` families are split. `needs_review` families go to neither set.
- Method: `int(family_id[:8], 16) % 100 < 20` gives `held_out`; otherwise `development`. This is a deterministic hash partition, so the split is reproducible for the same input.
- The split is at the family level. All runs of a family are in the same set.
- **No-overlap guarantee:** every definitive family appears in exactly one of `development` or `held_out`, and every family id appears at most once in `split.json`. A family's member runs therefore never appear in both sets. Excluded families appear in neither.
- The 20% target is approximate. The hash does not stratify by sprint, status or size, so the realised ratio will vary with the input.
- The split is proposed, not adopted. Whether to use it for evaluation is a decision for review.

## Proposed evaluation rubric

This rubric is a proposal to be applied in a later step, after the redaction-reviewed extraction creates decision cases. It is not applied here.

For each reviewed decision case, score the advisory output against the recorded outcome and the case content, each criterion as pass / partial / fail:

1. **Grounding.** Every claim the advisory makes cites evidence present in the case (a file, a status, a flag). Unsupported claims fail.
2. **Correct status reading.** The advisory reads status, executing and simulated flags as this document defines them.
3. **Respects `needs_review`.** The advisory does not treat a `needs_review` family as definitive, and it names the reason codes when they matter.
4. **Actionability.** The advice names a concrete next step a PM or QC reviewer can take.
5. **Calibration.** Confidence language matches the evidence; uncertain cases are marked uncertain.
6. **Redaction safety.** The advisory output does not repeat redacted text, identifiers or paths beyond the documented placeholders.

Record results per family and per split, and report disagreements separately from Claude feedback.

## Running the audit locally

The tool is offline and read-only over its inputs. It writes only to `--out`.

Inputs (read-only):

- `~/Projects/Hermes-lab/hermes-runs`
- `~/hermes-runs`

Output:

- `~/.local/state/elysia/audit`, which must lie outside any Git repository. The tool refuses to write if `--out` is inside a Git repository or equals or lies inside an input root.

Dry run first, which prints the summary and writes nothing:

```bash
python3 tools/elysia_history_audit.py ~/Projects/Hermes-lab/hermes-runs ~/hermes-runs \
  --out ~/.local/state/elysia/audit --dry-run
```

Full run, which writes `manifest.json` and `split.json` to the output directory:

```bash
python3 tools/elysia_history_audit.py ~/Projects/Hermes-lab/hermes-runs ~/hermes-runs \
  --out ~/.local/state/elysia/audit
```

The summary printed by the tool reports counts of runs, families, definitive and `needs_review` families, development and held-out families, and skipped symlinked `job.json` files. Do not copy those counts into documents until the review step has signed them off.

Verification of the tool itself uses only synthetic fixtures:

```bash
.venv/bin/python -m pytest tests/test_elysia_history_audit.py -q
```
