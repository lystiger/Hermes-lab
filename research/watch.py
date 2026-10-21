"""The RESEARCHER role's watch: fixed sources, dated findings, nothing acted on.

It contacts only hosts in ALLOWED_HOSTS, within a request budget, and reads structured release data
(JSON). Web page text is never followed, and nothing here installs, upgrades or edits anything.
Snapshots of each source are kept in the state folder, so the next run reports what changed.
"""

import argparse
import importlib.metadata
import json
import sys
import time
import urllib.parse
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import InvalidVersion, Version

import urllib.request

from security.urls import checked_urlopen

ALLOWED_HOSTS = {"pypi.org", "registry.npmjs.org", "api.github.com"}
DEFAULT_BUDGET = 60
USER_AGENT = "hermes-researcher/0.1 (read-only release watch)"


class ResearchError(RuntimeError):
    """A watch step cannot run: a host is not allowed, or the budget is spent."""


class Budget:
    def __init__(self, limit=DEFAULT_BUDGET):
        self.limit = limit
        self.used = 0

    def spend(self):
        if self.used >= self.limit:
            raise ResearchError(f"request budget of {self.limit} is spent")
        self.used += 1


def fetch_json(url, budget, timeout=15):
    """One JSON document from an allowed host. Refuses any other host before asking."""
    host = urllib.parse.urlsplit(url).hostname or ""
    if host not in ALLOWED_HOSTS:
        raise ResearchError(f"host {host!r} is not on the research allowlist")
    budget.spend()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with checked_urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def bump_kind(installed, latest):
    """'major', 'minor', 'patch', 'none', or 'unknown' when a version cannot be read."""
    try:
        old, new = Version(installed), Version(latest)
    except (InvalidVersion, TypeError):
        return "unknown"
    if new <= old:
        return "none"
    if new.major != old.major:
        return "major"
    if new.minor != old.minor:
        return "minor"
    return "patch"


def dependency_findings(requirements_path, budget, fetch=fetch_json):
    """For each requirement: the installed version against the latest release on PyPI."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    findings = []
    for line in Path(requirements_path).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name = Requirement(line).name
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            installed = None
        url = f"https://pypi.org/pypi/{name}/json"
        try:
            info = fetch(url, budget)["info"]
        except ResearchError as exc:
            findings.append({"package": name, "status": "UNPROVEN", "reason": str(exc)})
            continue
        latest = info.get("version")
        findings.append({
            "package": name,
            "installed": installed,
            "latest": latest,
            "bump": bump_kind(installed, latest) if installed else "not installed",
            "source": url,
            "retrieved": now,
            "notes_page": (info.get("project_urls") or {}).get("Changelog") or info.get("project_url"),
            "status": "FINDING",
        })
    return findings


def source_findings(sources, state_dir, budget, fetch=fetch_json):
    """Each watched value against its last snapshot. A first run only records the snapshot."""
    state = Path(state_dir)
    state.mkdir(parents=True, exist_ok=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    findings = []
    for source in sources:
        snapshot_path = state / f"{source['name']}.json"
        try:
            value = fetch(source["url"], budget)
            for key in source["field"].split("."):
                value = value[key]
        except (ResearchError, KeyError, TypeError) as exc:
            findings.append({"source": source["name"], "status": "UNPROVEN", "reason": str(exc)})
            continue
        previous = json.loads(snapshot_path.read_text())["value"] if snapshot_path.exists() else None
        snapshot_path.write_text(json.dumps({"value": value, "retrieved": now}))
        if previous is None:
            status = "RECORDED"
        else:
            status = "CHANGED" if previous != value else "UNCHANGED"
        findings.append({"source": source["name"], "project": source.get("project"), "url": source["url"],
                         "value": value, "previous": previous, "status": status, "retrieved": now})
    return findings


def run(requirements_path, sources_path, state_dir, budget_limit=DEFAULT_BUDGET, fetch=fetch_json):
    budget = Budget(budget_limit)
    sources = json.loads(Path(sources_path).read_text())
    return {
        "dependencies": dependency_findings(requirements_path, budget, fetch=fetch),
        "sources": source_findings(sources, state_dir, budget, fetch=fetch),
        "requests_used": budget.used,
        "note": "Release data only. Page text is not followed, and nothing is installed or changed.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only release watch for the research role")
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    args = parser.parse_args(argv)
    print(json.dumps(run(args.requirements, args.sources, args.state, args.budget), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
