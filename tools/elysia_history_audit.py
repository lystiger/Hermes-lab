"""Audit Hermes job history into run families and a family-level dev/held-out split.

Offline, read-only over the input roots, stdlib only. The audit records file names,
sizes, SHA-256 digests, stable identifiers and evidence flags. It never records
observations, error text, blocked reasons, prompts or transcripts.

Family rules (conservative):
- A retry link needs both the run-id prefix and the task graph (task/phase ids and roles)
  to match, and a retryHistory entry must name the other run.
- Any ambiguity marks the family needs_review and keeps it out of the split.
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

TERMINAL_STATUSES = {"COMPLETED", "BLOCKED", "FAILED", "CANCELLED"}
EVIDENCE_FILES = {
    "run_summary.json": "has_run_summary",
    "artifacts.json": "has_artifacts_json",
    "finalize.json": "has_finalize_json",
    "runner.log": "has_runner_log",
    "messages.jsonl": "has_messages",
}
JOB_FILE = "job.json"
MAX_JOB_BYTES = 50 * 1024 * 1024
HELD_OUT_PERCENT = 20
SCHEMA_VERSION = 1


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_dry(value):
    return isinstance(value, dict) and any(
        value.get(key) is True for key in ("dry_run", "dryRun", "simulated", "actor_dry_run"))


def _run_prefix(run_id):
    # A retry gets a new timestamp, so the prefix is the run id without its all-digit segments.
    return "_".join(part for part in run_id.split("_") if not part.isdigit())


def _task_graph(job):
    graph = []
    for kind, items in (("phase", job.get("phases")), ("task", job.get("tasks"))):
        for item in items or []:
            if isinstance(item, dict):
                ident = item.get("id") or item.get("task_id")
                graph.append((kind, str(ident), str(item.get("role"))))
    return sorted(graph)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _read_job(path):
    if path.stat().st_size > MAX_JOB_BYTES:
        return None, "job_json_too_large"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "job_json_unreadable"
    if not isinstance(data, dict):
        return None, "job_json_unreadable"
    return data, None


def _run_files(run_dir):
    """Regular files under a run folder, skipping nested run folders and symlinks."""
    records = []
    for dirpath, dirnames, filenames in os.walk(run_dir, followlinks=False):
        dirnames[:] = [name for name in dirnames if not (Path(dirpath) / name / JOB_FILE).exists()]
        for name in filenames:
            path = Path(dirpath) / name
            if path.is_symlink() or not path.is_file():
                continue
            if Path(dirpath) == run_dir and name == JOB_FILE:
                continue
            records.append({
                "filename": path.relative_to(run_dir).as_posix(),
                "size": path.stat().st_size,
                "sha256": _sha256_file(path),
            })
    return sorted(records, key=lambda record: record["filename"])


def scan_roots(roots):
    runs = []
    skipped = []
    for root in roots:
        root_key = _sha256_bytes(root.as_posix().encode("utf-8"))
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            if JOB_FILE not in filenames:
                continue
            run_dir = Path(dirpath)
            job_path = run_dir / JOB_FILE
            if job_path.is_symlink():
                skipped.append(job_path.as_posix())
                continue
            job, error = _read_job(job_path)
            files = _run_files(run_dir)
            run = {
                "root_key": root_key,
                "job_json": {"filename": JOB_FILE, "size": job_path.stat().st_size,
                             "sha256": _sha256_file(job_path)},
                "artifact_files": files,
                "reasons": [],
                "executing": False,
                "simulated": False,
            }
            evidence = {flag: any(f["filename"] == name for f in files)
                        for name, flag in EVIDENCE_FILES.items()}
            evidence["has_handoffs"] = any(f["filename"].startswith("handoffs/") for f in files)
            run["evidence"] = evidence
            if job is None:
                run.update({"id": None, "reasons": [error]})
                runs.append(run)
                continue
            status = str(job.get("status") or "").upper()
            completed = job.get("completedAt")
            branch = job.get("branch")
            run.update({
                "id": job.get("id"),
                "sprintId": job.get("sprintId"),
                "branch_sha256": _sha256_bytes(branch.encode("utf-8")) if isinstance(branch, str) else None,
                "status": status or None,
                "createdAt": job.get("createdAt"),
                "completedAt": completed,
                "executing": status not in TERMINAL_STATUSES or not completed,
                "simulated": _is_dry(job) or _is_dry(job.get("metadata"))
                or any(_is_dry(item) or (isinstance(item, dict) and _is_dry(item.get("metadata")))
                       for item in (job.get("tasks") or [])),
                "graph": _task_graph(job),
                "retry_strings": sorted({s for entry in (job.get("retryHistory") or [])
                                         for s in _strings(entry)}),
                "has_retry_history": bool(job.get("retryHistory")),
            })
            evidence.update({
                "has_verification": job.get("verification") is not None,
                "has_phases": bool(job.get("phases")),
            })
            runs.append(run)
    return runs, skipped


class _Union:
    def __init__(self, items):
        self.parent = {item: item for item in items}

    def find(self, item):
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def join(self, left, right):
        self.parent[self.find(left)] = self.find(right)


def build_families(runs):
    """Group runs into families and flag any ambiguity as needs_review."""
    by_id = {}
    for index, run in enumerate(runs):
        if run["id"] is None:
            run["reasons"].append("missing_id")
            continue
        by_id.setdefault(run["id"], []).append(index)
    for run_id, indexes in by_id.items():
        if len(indexes) > 1:
            for index in indexes:
                runs[index]["reasons"].append("duplicate_id")

    keyed = [i for i, run in enumerate(runs) if run["id"] is not None and len(by_id[run["id"]]) == 1]
    union = _Union(keyed)
    for index in keyed:
        run = runs[index]
        if run.get("executing"):
            run["reasons"].append("executing_run")
        if run.get("simulated"):
            run["reasons"].append("simulated_run")
        if not run.get("sprintId") or not run.get("status") or not run.get("createdAt"):
            run["reasons"].append("incomplete_record")
        if not run.get("graph"):
            run["reasons"].append("empty_task_graph")
        if run.get("has_retry_history"):
            linked = [other for other in keyed if other != index
                      and runs[other]["id"] in run["retry_strings"]]
            if not linked:
                run["reasons"].append("retry_link_unresolved")
            for other in linked:
                same = (_run_prefix(run["id"]) == _run_prefix(runs[other]["id"])
                        and run["graph"] == runs[other]["graph"])
                if same:
                    union.join(index, other)
                else:
                    run["reasons"].append("retry_link_mismatch")
                    runs[other]["reasons"].append("retry_link_mismatch")

    # Unlinked runs sharing prefix and task graph may be retries the history does not show.
    groups = {}
    for index in keyed:
        run = runs[index]
        if run.get("graph") is not None:
            key = (_run_prefix(run["id"]), json.dumps(run["graph"]))
            groups.setdefault(key, []).append(index)
    for indexes in groups.values():
        if len({union.find(i) for i in indexes}) > 1:
            for index in indexes:
                runs[index]["reasons"].append("unlinked_prefix_graph_match")

    members = {}
    for index in keyed:
        members.setdefault(union.find(index), []).append(index)
    families = []
    for indexes in members.values():
        ids = sorted(runs[i]["id"] for i in indexes)
        family_id = _sha256_bytes("\n".join(ids).encode("utf-8"))
        reasons = sorted({reason for i in indexes for reason in runs[i]["reasons"]})
        for i in indexes:
            runs[i]["family"] = family_id
        families.append({
            "family_id": family_id,
            "members": ids,
            "status": "needs_review" if reasons else "definitive",
            "reasons": reasons,
            "split": None,
        })
    # Runs without a usable unique id stand alone and never enter the split.
    for run in runs:
        if run.get("family") is None:
            family_id = _sha256_bytes(f"{run['root_key']}:{run['job_json']['sha256']}".encode("utf-8"))
            run["family"] = family_id
            families.append({
                "family_id": family_id,
                "members": [],
                "status": "needs_review",
                "reasons": sorted(set(run["reasons"])),
                "split": None,
            })
    for family in families:
        if family["status"] == "definitive":
            bucket = int(family["family_id"][:8], 16) % 100
            family["split"] = "held_out" if bucket < HELD_OUT_PERCENT else "development"
    return sorted(families, key=lambda family: family["family_id"])


def _public_run(run):
    return {
        "id": run.get("id"),
        "sprintId": run.get("sprintId"),
        "branch_sha256": run.get("branch_sha256"),
        "status": run.get("status"),
        "createdAt": run.get("createdAt"),
        "completedAt": run.get("completedAt"),
        "family_id": run.get("family"),
        "flags": {"executing": run.get("executing", False), "simulated": run.get("simulated", False)},
        "evidence": run.get("evidence", {}),
        "job_json": run["job_json"],
        "artifact_files": run.get("artifact_files", []),
        "reasons": sorted(set(run["reasons"])),
    }


def _resolve_roots(raw_roots):
    roots = []
    for raw in raw_roots:
        root = Path(raw).expanduser().resolve()
        if not root.is_dir():
            raise SystemExit(f"error: input root is not a directory: {raw}")
        roots.append(root)
    return roots


def _check_out(raw_out, roots):
    out = Path(raw_out).expanduser().resolve()
    for ancestor in [out, *out.parents]:
        if ancestor.name == ".git" or (ancestor / ".git").exists():
            raise SystemExit("error: --out must not be inside a git repository")
    for root in roots:
        if out == root or root in out.parents:
            raise SystemExit("error: --out must not equal or lie inside an input root")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline, read-only audit of Hermes job history: run families and a "
                    "family-level development/held-out split. Writes manifest.json and split.json to --out.")
    parser.add_argument("roots", nargs="+", help="input run roots to scan (read-only)")
    parser.add_argument("--out", required=True, help="output directory for manifest.json and split.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="scan and print the summary, but write nothing")
    args = parser.parse_args(argv)

    roots = _resolve_roots(args.roots)
    out = _check_out(args.out, roots)

    runs, skipped = scan_roots(roots)
    families = build_families(runs)
    development = [f["family_id"] for f in families if f["split"] == "development"]
    held_out = [f["family_id"] for f in families if f["split"] == "held_out"]
    excluded = [f["family_id"] for f in families if f["status"] == "needs_review"]
    summary = {
        "runs": len(runs),
        "families": len(families),
        "definitive_families": len([f for f in families if f["status"] == "definitive"]),
        "needs_review_families": len(excluded),
        "development_families": len(development),
        "held_out_families": len(held_out),
        "skipped_symlink_job_files": len(skipped),
        "dry_run": args.dry_run,
        "out": out.as_posix(),
    }
    if args.dry_run:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "tool": "elysia_history_audit",
        "roots_sha256": sorted(_sha256_bytes(root.as_posix().encode("utf-8")) for root in roots),
        "held_out_percent": HELD_OUT_PERCENT,
        "runs": [_public_run(run) for run in sorted(
            runs, key=lambda r: (r.get("id") or "", r["root_key"], r["job_json"]["sha256"]))],
        "families": families,
    }
    split = {
        "schema_version": SCHEMA_VERSION,
        "method": f"sha256(family_id)[:8] mod 100 < {HELD_OUT_PERCENT} -> held_out; definitive families only",
        "development": sorted(development),
        "held_out": sorted(held_out),
        "excluded_needs_review": sorted(excluded),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "split.json").write_text(json.dumps(split, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
