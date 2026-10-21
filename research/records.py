"""research_save: write sourced findings into LysStack/research/. Refuses any finding without a source.

A finding needs a claim, an https source link, and the date it was retrieved. Existing research files
are never overwritten, so each topic keeps its first record and a new question gets a new file.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
REQUIRED = ("claim", "source_url", "retrieved")


class RecordError(ValueError):
    """A finding or topic cannot be saved as research."""


def _cell(text):
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip()


def save_research(topic, findings, root, date=None):
    if not SLUG.match(topic or ""):
        raise RecordError("topic must be lowercase letters, digits and hyphens")
    if not findings:
        raise RecordError("research needs at least one finding")
    for number, finding in enumerate(findings, 1):
        missing = [key for key in REQUIRED if not str(finding.get(key) or "").strip()]
        if missing:
            raise RecordError(f"finding {number} has no {', '.join(missing)}")
        if not str(finding["source_url"]).startswith("https://"):
            raise RecordError(f"finding {number} needs an https source link")
    target = Path(root) / "research" / f"{topic}.md"
    if target.exists():
        raise RecordError(f"research '{topic}' already exists; choose a new topic name")
    lines = [
        f"# Research: {topic}", "",
        f"- **Recorded:** {date or time.strftime('%Y-%m-%d')}",
        "- **Status:** Findings for planning. Nothing here is a decision.", "",
        "| # | Claim | Source | Retrieved | Quote | Licence | Status |",
        "|---|---|---|---|---|---|---|",
    ]
    for number, f in enumerate(findings, 1):
        lines.append(
            f"| {number} | {_cell(f['claim'])} | {_cell(f['source_url'])} | {_cell(f['retrieved'])} "
            f"| {_cell(f.get('quote'))} | {_cell(f.get('licence'))} | {_cell(f.get('status') or 'recorded')} |"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description="Save sourced research into LysStack")
    parser.add_argument("--root", required=True, type=Path, help="LysStack repository")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--findings", required=True, type=Path, help="JSON list of findings")
    args = parser.parse_args(argv)
    try:
        path = save_research(args.topic, json.loads(args.findings.read_text()), args.root)
    except RecordError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
