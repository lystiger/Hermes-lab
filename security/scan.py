"""The SECURITY role's deterministic checks: secrets, Python injection patterns, and dependency advisories.

Each check reports PASS, FAIL or UNPROVEN. UNPROVEN means the check could not run here (for
example, a scanner is not installed), so it is never reported as a pass. The scan reads the
repository and changes nothing. It makes no network calls except the dependency audit, which
asks the advisory database about pinned packages.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__", ".mypy_cache", ".pytest_cache"}
MAX_FILE_BYTES = 512 * 1024

# Each rule: a name and a pattern. Patterns match the shape of a credential, not a value.
SECRET_RULES = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "model-api-key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "assigned-secret": re.compile(
        r"""(?i)[\w-]*(api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*['"][^'"\s]{12,}['"]"""),
}


def _text_files(root):
    for path in Path(root).rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue


# A line that carries this marker is a test fixture with a fake value, and is not reported.
FIXTURE_MARKER = "secret-scan: fixture"


def _mask(text):
    return text[:4] + "****" if len(text) > 4 else "****"


def scan_secrets(root):
    findings = []
    for path, text in _text_files(root):
        for number, line in enumerate(text.splitlines(), 1):
            if FIXTURE_MARKER in line:
                continue
            for rule, pattern in SECRET_RULES.items():
                match = pattern.search(line)
                if match:
                    findings.append({"rule": rule, "file": str(path.relative_to(root)), "line": number,
                                     "severity": "high", "evidence": _mask(match.group(0))})
    return {"check": "secrets", "status": "FAIL" if findings else "PASS", "findings": findings}


def _run_json(argv, cwd):
    try:
        result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    try:
        return json.loads(result.stdout or "null"), result.stderr.strip()[:300]
    except json.JSONDecodeError:
        return None, (result.stderr or result.stdout).strip()[:300]


def scan_python(root):
    """Injection and unsafe-call patterns in Python, via bandit (shell=True, eval, SQL built from strings, pickle...)."""
    if shutil.which("bandit") is None and not _module_present("bandit"):
        return {"check": "python-static", "status": "UNPROVEN", "reason": "bandit is not installed", "findings": []}
    if not any(Path(root).rglob("*.py")):
        return {"check": "python-static", "status": "PASS", "findings": []}
    # Vendored code, tests (asserts are their job) and B101 are out of scope for the product check.
    argv = [sys.executable, "-m", "bandit", "-r", ".", "-f", "json", "-q", "-s", "B101",
            "-x", ",".join(f"./{d}" for d in sorted(SKIP_DIRS | {"tests"}))]
    data, error = _run_json(argv, root)
    if not isinstance(data, dict) or "results" not in data:
        return {"check": "python-static", "status": "UNPROVEN", "reason": error or "bandit gave no result",
                "findings": []}
    findings = [{"rule": r["test_id"], "file": r["filename"].removeprefix("./"), "line": r["line_number"],
                 "severity": r["issue_severity"].lower(), "evidence": r["issue_text"]} for r in data["results"]]
    # Medium and high findings fail the check. Low ones are notes, so they do not drown the signal.
    blocking = [f for f in findings if f["severity"] in ("medium", "high")]
    notes = [f for f in findings if f["severity"] not in ("medium", "high")]
    return {"check": "python-static", "status": "FAIL" if blocking else "PASS", "findings": blocking, "notes": notes}


def scan_dependencies(root):
    """Known advisories for pinned Python packages, via pip-audit against requirements.txt."""
    requirements = Path(root) / "requirements.txt"
    if not requirements.is_file():
        return {"check": "dependencies", "status": "UNPROVEN", "reason": "no requirements.txt", "findings": []}
    if not _module_present("pip_audit"):
        return {"check": "dependencies", "status": "UNPROVEN", "reason": "pip-audit is not installed", "findings": []}
    data, error = _run_json([sys.executable, "-m", "pip_audit", "-r", str(requirements), "-f", "json", "--progress-spinner", "off"], root)
    if not isinstance(data, dict) or "dependencies" not in data:
        return {"check": "dependencies", "status": "UNPROVEN", "reason": error or "pip-audit gave no result",
                "findings": []}
    findings = []
    for dep in data["dependencies"]:
        for vuln in dep.get("vulns", []):
            findings.append({"rule": vuln.get("id"), "package": dep.get("name"), "version": dep.get("version"),
                             "severity": "high", "evidence": ", ".join(vuln.get("fix_versions", [])) or "no fix listed"})
    return {"check": "dependencies", "status": "FAIL" if findings else "PASS", "findings": findings}


def _module_present(name):
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def report(root):
    checks = [scan_secrets(root), scan_python(root), scan_dependencies(root)]
    if any(c["status"] == "FAIL" for c in checks):
        verdict = "FAIL"
    elif any(c["status"] == "UNPROVEN" for c in checks):
        verdict = "UNPROVEN"
    else:
        verdict = "PASS"
    return {"verdict": verdict, "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Security checks for a repository (read-only)")
    parser.add_argument("--repo", required=True, type=Path)
    args = parser.parse_args(argv)
    result = report(args.repo.resolve())
    print(json.dumps(result, indent=2))
    return 1 if result["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
