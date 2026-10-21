"""Regenerate README.md, so the diagrams render on GitHub as Mermaid blocks. Design output only."""

from pathlib import Path

HERE = Path(__file__).resolve().parent
TITLES = {"sitemap": "Sitemap", "buyer-flow": "Buyer flow: product to quotation request",
          "staff-flow": "Staff flow", "inquiry-status": "Inquiry status lifecycle",
          "submit-sequence": "Submitting an inquiry", "database": "Database (generated from the staging schema)"}


def main():
    parts = ["# Unigreen diagrams", "",
             "Each diagram is Mermaid source. GitHub draws the blocks below. To render one elsewhere,",
             "paste its block into the [Mermaid Live Editor](https://mermaid.live).",
             "Regenerate this page with `python3 build_readme.py` after editing a source in `src/`.", ""]
    for key, title in TITLES.items():
        lines = (HERE / "src" / f"{key}.mmd").read_text(encoding="utf-8").splitlines()
        status = next((l[3:].strip() for l in lines if l.startswith("%% status:")), "")
        body = "\n".join(l for l in lines if not l.startswith("%% status:")).strip()
        parts += [f"## {title}", ""]
        if status:
            parts += [f"_{status}_", ""]
        parts += ["```mermaid", body, "```", ""]
    (HERE / "README.md").write_text("\n".join(parts), encoding="utf-8")
    print("wrote README.md")


if __name__ == "__main__":
    main()
