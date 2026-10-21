import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "designs" / "unigreen" / "wireframes"))
import build  # noqa: E402


@pytest.fixture
def paths(tmp_path, monkeypatch):
    decisions = tmp_path / "decisions.md"
    monkeypatch.setenv("HERMES_DECISIONS", str(decisions))
    public = tmp_path / "public"
    (public / "wireframes").mkdir(parents=True)
    (public / "manifest.json").write_text('{"project": "unigreen"}')
    monkeypatch.setattr(build, "PUBLIC", public)
    monkeypatch.setattr(build, "UNIGREEN", tmp_path / "unigreen")
    (tmp_path / "unigreen" / "tokens").mkdir(parents=True)
    (tmp_path / "unigreen" / "tokens" / "b-clean-eco.css").write_text(":root { --primary: #1d6b36; }")
    monkeypatch.setattr(build, "HERE", tmp_path / "unigreen" / "wireframes")
    return decisions


def test_nothing_is_written_while_no_direction_is_chosen(paths, tmp_path):
    assert build.main() == 0
    assert not (tmp_path / "public" / "wireframes" / "home.html").exists()


def test_each_screen_is_written_and_listed(paths, tmp_path):
    paths.write_text("""
### Decision: Design direction — B · Clean eco

- **Direction:** b-clean-eco
- **Decision:** B · Clean eco
- **Reason:** Clear for buyers and calm.
- **Status:** accepted
""")

    assert build.main() == 0

    assert len(list((tmp_path / "public" / "wireframes").glob("*.html"))) == len(build.SCREENS)
    html = (tmp_path / "public" / "wireframes" / "home.html").read_text()
    assert "--primary: #1d6b36" in html and "wireframe" in html
    assert "wireframes" in (tmp_path / "public" / "manifest.json").read_text()
