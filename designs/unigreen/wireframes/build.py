"""Write HTML wireframes for the key Unigreen screens, in the direction Lystiger chose.

Reads the recorded decision from LysStack (read-only). If nothing is chosen, it writes nothing.
Writes out/wireframes/*.html, copies them to LysControl's public folder, and lists them in the manifest.
Design output only: no product code.
"""

import json
import os
import re
import shutil
import sys
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIGREEN = HERE.parent
PUBLIC = UNIGREEN.parent.parent / "console" / "public" / "design" / "unigreen"
sys.path.insert(0, str(UNIGREEN.parent.parent))

from design_decision.decision import current_decision  # noqa: E402

SCREENS = {
    "home": ("Home", ["Logo and main menu", "Hero: what Unigreen makes, with one call to action", "Product categories", "Request a quotation"]),
    "product": ("Product detail", ["Breadcrumb", "Pack image and name", "Formats, pack sizes and specs", "Add to quotation list", "Related products"]),
    "quotation-list": ("Quotation list", ["Line items: product, format, quantity", "Remove a line", "Contact form: name, email, company, phone, notes", "Send quotation request"]),
    "inquiry-sent": ("Thank you", ["Confirmation and reference", "Written pricing in two working days", "Back to products"]),
    "staff-inquiries": ("Staff: inquiries", ["Search and status filter", "Table: reference, company, status, assigned to", "Open an inquiry"]),
}

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · wireframe</title>
<style>
{tokens}
body {{ margin: 0; background: var(--bg); color: var(--text); font: 16px/1.5 var(--font); }}
main {{ max-width: 960px; margin: 0 auto; padding: 16px; display: flex; flex-direction: column; gap: var(--gap); }}
.block {{ background: var(--surface); border: 1px dashed var(--muted); border-radius: var(--radius); padding: 16px; }}
.block h2 {{ margin: 0 0 8px; font-size: 13px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); font-weight: 600; }}
.block p {{ margin: 0; }}
button {{ min-height: 44px; padding: 0 16px; border-radius: var(--radius); border: 1px solid var(--primary); background: var(--primary); color: var(--on-primary); font: inherit; }}
button.secondary {{ background: transparent; color: var(--primary); }}
@media (max-width: 600px) {{ main {{ padding: 12px; }} }}
</style></head>
<body><main>
<p class="block"><strong>{title}</strong> · wireframe in direction {label}. Layout only; the spec sets the look.</p>
{blocks}
</main></body></html>
"""


def block(text):
    return f'<section class="block"><h2>{escape(text)}</h2><p>{escape(text)}</p></section>'


def wireframe(key, title, parts, tokens_css, label):
    blocks = "\n".join(block(p) for p in parts)
    if key == "quotation-list":
        blocks += '\n<section class="block"><button type="button">Send quotation request</button> <button type="button" class="secondary">Keep browsing</button></section>'
    return PAGE.format(title=escape(title), label=escape(label), tokens=tokens_css, blocks=blocks)


def main():
    decisions = Path(os.environ.get(
        "HERMES_DECISIONS", Path.home() / "Projects" / "LysStack" / "projects" / "unigreen" / "decisions.md"))
    decision = current_decision(decisions)
    if not decision or not decision.get("direction"):
        print("No design direction is chosen yet; nothing written.")
        return 0
    token_file = UNIGREEN / "tokens" / f"{decision['direction']}.css"
    if not token_file.is_file():
        print(f"No tokens for {decision['direction']}.")
        return 1
    tokens = token_file.read_text(encoding="utf-8")
    out = HERE.parent / "out" / "wireframes"
    out.mkdir(parents=True, exist_ok=True)
    PUBLIC.joinpath("wireframes").mkdir(parents=True, exist_ok=True)
    names = []
    for key, (title, parts) in SCREENS.items():
        html = wireframe(key, title, parts, tokens, decision["label"])
        (out / f"{key}.html").write_text(html, encoding="utf-8")
        shutil.copy(out / f"{key}.html", PUBLIC / "wireframes" / f"{key}.html")
        names.append({"id": key, "label": title, "file": f"wireframes/{key}.html"})
    manifest_path = PUBLIC / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["wireframes"] = names
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(names)} wireframes in direction {decision['direction']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
