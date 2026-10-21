"""Write the design spec for the direction Lystiger chose, from its tokens and the contrast report.

Reads the recorded decision from LysStack (read-only). If nothing is chosen, it writes nothing.
Design output only: no product code.
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKENS = HERE / "tokens"
OUT = HERE / "spec"
sys.path.insert(0, str(HERE.parent.parent))

from design_decision.decision import current_decision  # noqa: E402


def tokens_of(css):
    return dict(re.findall(r"--([a-z-]+):\s*([^;]+);", css))


def spec_for(direction, css, contrast, label, reason):
    t = tokens_of(css)
    rows = "\n".join(f"| {k} | `{v.strip()}` |" for k, v in t.items())
    contrast_rows = "\n".join(f"| {name} | {c['ratio']} : 1 | {'passes AA' if c['wcag_aa_text'] else 'fails AA'} |"
                              for name, c in contrast.items())
    return f"""# Design spec: {label}

_Chosen by Lystiger. Reason: {reason}_

Design output only. Product code is built by BUILDER from this spec.

## Tokens

| Token | Value |
| --- | --- |
{rows}

## Contrast (computed)

| Pair | Ratio | WCAG AA text |
| --- | --- | --- |
{contrast_rows}

## Components and states

- **Primary button:** default, hover, focus (visible ring), disabled (45% opacity). Text in `--on-primary`.
- **Secondary button:** outline in `--primary`, same states.
- **Product card:** surface, `--radius`, pack image on a neutral ground, name, meta, Add to quotation.
- **Form field:** default, focus, error (border in the error colour, message below), disabled.
- **Basket drawer:** list of lines, quantity, unit, remove; empty state; send button.

## Layout and motion

- Spacing gap: `--gap`. Radius: `--radius`.
- Entry transitions 260 ms, hover 160 ms, standard easing. No looping animation (reduced motion turns off transitions).
- Touch targets at least 44 px on phone width.

## Copy

Use the English and Vietnamese strings in `designs/unigreen/build.py`. Vietnamese must hold on phone width.

## Diagrams

See `designs/unigreen/diagrams/README.md` for the sitemap, flows, sequence, status lifecycle and database.
"""


def main():
    decisions = Path(__import__("os").environ.get(
        "HERMES_DECISIONS", Path.home() / "Projects" / "LysStack" / "projects" / "unigreen" / "decisions.md"))
    decision = current_decision(decisions)
    if not decision or not decision.get("direction"):
        print("No design direction is chosen yet; nothing written.")
        return 0
    direction = decision["direction"]
    token_file = TOKENS / f"{direction}.css"
    if not token_file.is_file():
        print(f"No tokens for {direction}.")
        return 1
    contrast = json.loads((HERE / "out" / "contrast.json").read_text())[direction]
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"SPEC-{direction}.md"
    target.write_text(spec_for(direction, token_file.read_text(), contrast, decision["label"], decision["reason"]),
                      encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
