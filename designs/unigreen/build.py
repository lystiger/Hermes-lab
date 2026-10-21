"""Build the three direction pages, a comparison sheet, and contrast ratios. Design output only, no product code."""

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKENS = sorted((HERE / "tokens").glob("*.css"))
TEMPLATE = (HERE / "template.html").read_text(encoding="utf-8")
OUT = HERE / "out"


def tokens_of(css):
    return dict(re.findall(r"--([a-z-]+):\s*([^;]+);", css))


def luminance(hex_color):
    channels = [int(hex_color.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return round((hi + 0.05) / (lo + 0.05), 2)


def contrast_report(values):
    pairs = {
        "text on background": ("text", "bg"),
        "button text on primary": ("on-primary", "primary"),
        "muted text on background": ("muted", "bg"),
    }
    return {name: {"ratio": contrast(values[a], values[b]), "wcag_aa_text": contrast(values[a], values[b]) >= 4.5}
            for name, (a, b) in pairs.items()}


def main():
    OUT.mkdir(exist_ok=True)
    report = {}
    pages = []
    for path in TOKENS:
        name = path.stem
        css = path.read_text(encoding="utf-8")
        page = TEMPLATE.replace("/*TOKENS*/", css)
        (OUT / f"{name}.html").write_text(page, encoding="utf-8")
        values = tokens_of(css)
        report[name] = contrast_report(values)
        pages.append(name)
    cells = "".join(
        f'<figure><figcaption>{name}</figcaption><iframe src="{name}.html" width="1280" height="900" '
        f'style="transform:scale(.42);transform-origin:0 0;width:1280px;height:900px;border:0"></iframe></figure>'
        for name in pages)
    sheet = ("<!doctype html><meta charset='utf-8'><style>body{margin:0;background:#888;font-family:system-ui}"
             "figure{margin:0;width:540px;height:400px;overflow:hidden;background:#fff;display:inline-block;vertical-align:top;margin:8px}"
             "figcaption{background:#222;color:#fff;padding:4px 8px;font-size:14px}iframe{display:block}</style>"
             f"<div style='width:1700px'>{cells}</div>")
    (OUT / "sheet.html").write_text(sheet, encoding="utf-8")
    (OUT / "contrast.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
