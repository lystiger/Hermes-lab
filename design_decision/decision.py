"""Record the design direction Lystiger chooses, as a human decision in LysStack.

The choice is written to projects/<project>/decisions.md, where agents read decisions first. Nothing is
committed automatically: the decision file is changed in the working tree, for Lystiger to review and commit.
A new choice supersedes the previous one; the earlier entry is kept and marked superseded.
"""

import json
import re
import time
from pathlib import Path

HEADING = "### Decision: Design direction"
ENTRY = re.compile(r"^### Decision: Design direction — (?P<label>.+)$", re.MULTILINE)


class DecisionError(ValueError):
    """The choice cannot be recorded."""


def load_directions(manifest_path):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    return {d["id"]: d["label"] for d in manifest["directions"]}


def current_decision(decisions_path):
    """The latest accepted design direction, or None."""
    path = Path(decisions_path)
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    entries = list(ENTRY.finditer(text))
    if not entries:
        return None
    last = entries[-1]
    block = text[last.end():]
    block = block.split("\n### ", 1)[0]
    if "Status: superseded" in block:
        return None
    direction = re.search(r"\*\*Direction:\*\*\s*(\S+)", block)
    reason = re.search(r"\*\*Reason:\*\*\s*(.+)", block)
    date = re.search(r"\*\*Date:\*\*\s*(\S+)", block)
    return {"direction": direction.group(1) if direction else None, "label": last.group("label").strip(),
            "reason": reason.group(1).strip() if reason else "", "date": date.group(1) if date else None}


def record_decision(decisions_path, manifest_path, direction, reason, date=None):
    directions = load_directions(manifest_path)
    if direction not in directions:
        raise DecisionError(f"unknown direction {direction!r}; choose one of {', '.join(directions)}")
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise DecisionError("give a reason of at least ten characters")
    path = Path(decisions_path)
    previous = current_decision(path)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if previous and previous["direction"] == direction:
        raise DecisionError(f"{directions[direction]} is already the chosen direction")
    if previous:
        # Keep the old entry, marked superseded, so the history stays readable.
        last = list(ENTRY.finditer(text))[-1]
        head, tail = text[:last.end()], text[last.end():]
        tail = tail.replace("- **Status:** accepted", "- **Status:** superseded", 1)
        text = head + tail
    rejected = [label for key, label in directions.items() if key != direction]
    entry = "\n".join([
        "",
        f"{HEADING} — {directions[direction]}",
        "",
        f"- **Date:** {date or time.strftime('%Y-%m-%d')}",
        "- **Source:** human (Lystiger)",
        "- **Problem:** Which design direction should Unigreen follow?",
        f"- **Direction:** {direction}",
        f"- **Decision:** {directions[direction]}",
        f"- **Reason:** {reason}",
        f"- **Rejected:** {', '.join(rejected)}",
        "- **Status:** accepted",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip("\n") + "\n" + entry, encoding="utf-8")
    return {"direction": direction, "label": directions[direction], "reason": reason,
            "superseded": previous["direction"] if previous else None}
