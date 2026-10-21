"""The PRODUCTION role's release gate: decides whether a change is ready to merge to main.

It reads evidence that other checks produced and reports PASS, FAIL or UNPROVEN. It never deploys:
production is deployed by a human after merging to main. Trials run on staging, before the merge.

Tiers, chosen from the files a change touches:
  full   user-facing or data changes: tests, security scan, and the staging user-flow run
  smoke  other code: tests and security scan
  skip   docs-only change: nothing to trial
"""

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED = {
    "full": ("tests", "security", "staging_flows"),
    "smoke": ("tests", "security"),
    "skip": (),
}
USER_FACING = re.compile(r"(^|/)(app|components|pages|routes|public|views)/|\.(tsx|jsx|html|css)$")
DATA = re.compile(r"(^|/)(migrations|models|schema|alembic)|models\.py$|\.sql$")
DOCS = re.compile(r"\.(md|txt|rst)$|^docs/")


def classify(changed_files):
    """The tier a change needs, from the paths it touches. Unknown paths get the full tier."""
    files = [f for f in changed_files if f]
    if not files:
        return "smoke"
    if all(DOCS.search(f) for f in files):
        return "skip"
    if any(USER_FACING.search(f) or DATA.search(f) for f in files):
        return "full"
    if all(re.search(r"^(tests|scripts)/|\.(py|ts|tsx|js|mjs)$", f) for f in files):
        return "smoke"
    return "full"


def _status(name, evidence):
    if evidence is None:
        return {"check": name, "status": "UNPROVEN", "reason": "no evidence was provided"}
    if name == "tests":
        failed = int(evidence.get("failed", 0)) + int(evidence.get("errors", 0))
        ok = evidence.get("passed", 0) > 0 and failed == 0
        return {"check": name, "status": "PASS" if ok else "FAIL",
                "reason": f"{evidence.get('passed', 0)} passed, {failed} failed or errored"}
    if name == "security":
        return {"check": name, "status": evidence.get("verdict", "UNPROVEN"),
                "reason": "security scan verdict"}
    if name == "staging_flows":
        failed = int(evidence.get("failed", 0))
        total = int(evidence.get("total", 0))
        if total == 0:
            return {"check": name, "status": "UNPROVEN", "reason": "the flow run recorded no checks"}
        return {"check": name, "status": "PASS" if failed == 0 else "FAIL",
                "reason": f"{total - failed} of {total} checks passed"}
    return {"check": name, "status": "UNPROVEN", "reason": "unknown check"}


def readiness(tier, evidence):
    """The gate's verdict for a tier, given the evidence dict keyed by check name."""
    if tier not in REQUIRED:
        raise ValueError(f"tier must be one of {', '.join(REQUIRED)}")
    if tier == "skip":
        return {"tier": tier, "verdict": "PASS", "checks": [], "blocked_by": []}
    checks = [_status(name, evidence.get(name)) for name in REQUIRED[tier]]
    blocked = [c["check"] for c in checks if c["status"] == "FAIL"]
    if blocked:
        verdict = "FAIL"
    elif any(c["status"] == "UNPROVEN" for c in checks):
        verdict = "UNPROVEN"
    else:
        verdict = "PASS"
    return {"tier": tier, "verdict": verdict, "checks": checks, "blocked_by": blocked}


def load_evidence(folder):
    folder = Path(folder)
    names = {"tests": "tests.json", "security": "security.json", "staging_flows": "staging-flows.json"}
    evidence = {}
    for name, filename in names.items():
        path = folder / filename
        if path.is_file():
            evidence[name] = json.loads(path.read_text(encoding="utf-8"))
    return evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description="Release readiness for a change (never deploys)")
    parser.add_argument("--evidence", required=True, type=Path, help="folder with tests.json, security.json, staging-flows.json")
    parser.add_argument("--files", nargs="*", default=None, help="changed files; the tier is classified from them")
    parser.add_argument("--tier", choices=sorted(REQUIRED), help="override the classified tier")
    args = parser.parse_args(argv)
    tier = args.tier or classify(args.files or [])
    result = readiness(tier, load_evidence(args.evidence))
    print(json.dumps(result, indent=2))
    return 1 if result["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
