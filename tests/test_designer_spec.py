import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "designs" / "unigreen"))
import spec_build  # noqa: E402


@pytest.fixture
def paths(tmp_path, monkeypatch):
    decisions = tmp_path / "decisions.md"
    monkeypatch.setenv("HERMES_DECISIONS", str(decisions))
    monkeypatch.setattr(spec_build, "OUT", tmp_path / "spec")
    return decisions


def test_nothing_is_written_while_no_direction_is_chosen(paths, tmp_path):
    assert spec_build.main() == 0
    assert not (tmp_path / "spec").exists()


def test_the_chosen_direction_gets_its_spec(paths, tmp_path):
    paths.write_text("""
### Decision: Design direction — B · Clean eco

- **Direction:** b-clean-eco
- **Decision:** B · Clean eco
- **Reason:** Clear for buyers and calm.
- **Status:** accepted
""")

    assert spec_build.main() == 0

    text = (tmp_path / "spec" / "SPEC-b-clean-eco.md").read_text()
    assert "# Design spec: B · Clean eco" in text
    assert "| primary |" in text and "Clear for buyers and calm." in text


def test_the_designer_profile_is_design_only():
    roles = json.loads((ROOT / "config" / "roles.json").read_text())

    assert roles["designer"]["may_edit_product_source"] is False
    assert roles["designer"]["network"] is False
    assert roles["designer"]["may_deploy_to_production"] is False
