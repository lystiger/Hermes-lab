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


DETAIL_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{name} detail</title>
<style>{css}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text); font-family: var(--font); font-size: 16px; line-height: 1.5; padding: 32px; width: 1200px; }}
h1 {{ font-size: 32px; margin: 0 0 4px; }} h2 {{ font-size: 20px; margin: 32px 0 12px; border-bottom: 1px solid color-mix(in srgb, var(--text) 15%, transparent); padding-bottom: 6px; }}
.muted {{ color: var(--muted); font-size: 14px; }}
.row {{ display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-start; }}
.sw {{ width: 150px; }} .sw div {{ height: 72px; border-radius: var(--radius); border: 1px solid color-mix(in srgb, var(--text) 12%, transparent); }}
.sw small {{ display: block; font-size: 13px; color: var(--muted); margin-top: 4px; }}
.btn {{ display: inline-block; padding: 10px 18px; border-radius: var(--radius); font-weight: 700; border: 2px solid var(--primary); background: var(--primary); color: var(--on-primary); }}
.btn.outline {{ background: transparent; color: var(--primary); }}
.btn.disabled {{ opacity: .45; }}
.btn.focus {{ outline: 3px solid var(--accent); outline-offset: 2px; }}
.field {{ display: flex; flex-direction: column; gap: 4px; width: 260px; font-size: 14px; color: var(--muted); }}
.field input {{ padding: 10px 12px; border-radius: var(--radius); border: 1px solid color-mix(in srgb, var(--text) 30%, transparent); background: var(--surface); color: var(--text); font: inherit; }}
.field.error input {{ border: 2px solid #b3123f; }} .field.error .msg {{ color: #b3123f; font-size: 13px; }}
.tbl {{ width: 100%; border-collapse: collapse; font-size: 14px; }} .tbl td {{ padding: 8px; border-bottom: 1px solid color-mix(in srgb, var(--text) 10%, transparent); vertical-align: top; }}
.tbl td:first-child {{ color: var(--muted); width: 200px; }}
.box {{ width: 150px; padding: 14px; background: var(--surface); border-radius: var(--radius); }}
</style></head><body>
<h1>{name}</h1><p class="muted">Tokens applied from tokens/{name}.css. Contrast values are computed, not judged.</p>

<h2>Colour</h2>
<div class="row">{swatches}</div>
<table class="tbl" style="margin-top:12px">{contrast_rows}</table>

<h2>Type</h2>
<table class="tbl">
<tr><td>Display · 44px / 1.1</td><td style="font-size:44px;line-height:1.1;font-weight:700">Tissue rolls for every day</td></tr>
<tr><td>Heading · 28px / 1.2</td><td style="font-size:28px;font-weight:700">Request a quotation</td></tr>
<tr><td>Body · 16px / 1.5</td><td>Written pricing within two working days, for the pack sizes and formats you choose.</td></tr>
<tr><td>Small · 14px / 1.4</td><td style="font-size:14px;color:var(--muted)">Coreless · 3 ply · 10 rolls</td></tr>
<tr><td>Vietnamese · body</td><td lang="vi">Giấy vệ sinh cao cấp, không lõi, tiết kiệm hơn cho mọi gia đình.</td></tr>
</table>

<h2>Buttons and focus</h2>
<div class="row">
<span class="btn">Primary</span>
<span class="btn outline">Secondary</span>
<span class="btn disabled">Disabled</span>
<span class="btn focus">Focused</span>
</div>

<h2>Form fields</h2>
<div class="row">
<label class="field">Contact name<input value="Nguyễn Thị Hoa"></label>
<label class="field error">Email<input value="hoa@example"><span class="msg">Enter an email address such as name@company.com</span></label>
</div>

<h2>Spacing, radius and cards</h2>
<div class="row">
<div class="box" style="border-radius:var(--radius)"><b>Card</b><div class="muted">radius {radius}</div></div>
<div class="box" style="padding:var(--gap)"><b>Gap</b><div class="muted">{gap} between items</div></div>
</div>

<h2>Copy: English and Vietnamese</h2>
<table class="tbl">{copy_rows}</table>
</body></html>"""

COPY = [
    ("Hero heading", "Tissue rolls for every day", "Giấy vệ sinh cho mọi ngày"),
    ("Primary action", "Request a quotation", "Yêu cầu báo giá"),
    ("Product action", "Add to quotation", "Thêm vào báo giá"),
    ("Empty basket", "Your quotation list is empty", "Danh sách báo giá đang trống"),
    ("Submitted", "Thank you. We will reply with written pricing within two working days.",
     "Cảm ơn bạn. Chúng tôi sẽ gửi báo giá bằng văn bản trong hai ngày làm việc."),
    ("Required field error", "Please enter your contact name", "Vui lòng nhập tên người liên hệ"),
    ("Email error", "Enter an email address such as name@company.com", "Nhập email, ví dụ name@company.com"),
]


def detail_page(name, css, values):
    swatch_keys = [("bg", "Background"), ("surface", "Surface"), ("text", "Text"), ("muted", "Muted text"),
                   ("primary", "Primary"), ("on-primary", "On primary"), ("accent", "Accent")]
    swatches = "".join(
        f'<div class="sw"><div style="background:var(--{key})"></div><small>{label} · {values[key]}</small></div>'
        for key, label in swatch_keys)
    rows = []
    for label, a, b in [("text on background", "text", "bg"), ("muted on background", "muted", "bg"),
                        ("button text on primary", "on-primary", "primary"), ("text on surface", "text", "surface")]:
        ratio = contrast(values[a], values[b])
        rows.append(f"<tr><td>{label}</td><td>{ratio} : 1 · {'passes AA' if ratio >= 4.5 else 'fails AA'}</td></tr>")
    copy_rows = "".join(f"<tr><td>{k}</td><td>{en}</td><td lang='vi'>{vi}</td></tr>" for k, en, vi in COPY)
    copy_rows = f"<tr><td></td><td><b>English</b></td><td><b>Tiếng Việt</b></td></tr>{copy_rows}"
    return DETAIL_TEMPLATE.format(name=name, css=css, swatches=swatches, contrast_rows="".join(rows),
                                  copy_rows=copy_rows, radius=values["radius"], gap=values["gap"])


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
        (OUT / f"detail-{name}.html").write_text(detail_page(name, css, values), encoding="utf-8")
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
