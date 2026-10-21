import json

import pytest

from design_decision.decision import DecisionError, current_decision, record_decision

MANIFEST = {"directions": [
    {"id": "a-family-fresh", "label": "A · Family fresh"},
    {"id": "b-clean-eco", "label": "B · Clean eco"},
    {"id": "c-japanese-precision", "label": "C · Japanese precision"},
]}
REASON = "Matches the family packs and stays readable for buyers."


@pytest.fixture
def paths(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(MANIFEST))
    return tmp_path / "decisions.md", manifest


def test_a_first_choice_is_recorded_with_its_reason_and_rejections(paths):
    decisions, manifest = paths
    decisions.write_text("# Decisions\n\nExisting history stays.\n")

    result = record_decision(decisions, manifest, "b-clean-eco", REASON, date="2026-10-21")

    text = decisions.read_text()
    assert result["label"] == "B · Clean eco" and result["superseded"] is None
    assert "Existing history stays." in text
    assert "### Decision: Design direction — B · Clean eco" in text
    assert "- **Reason:** " + REASON in text
    assert "- **Rejected:** A · Family fresh, C · Japanese precision" in text
    assert current_decision(decisions)["direction"] == "b-clean-eco"


def test_a_new_choice_supersedes_the_old_one_and_keeps_it(paths):
    decisions, manifest = paths
    record_decision(decisions, manifest, "a-family-fresh", REASON, date="2026-10-21")

    result = record_decision(decisions, manifest, "c-japanese-precision", REASON, date="2026-10-22")

    text = decisions.read_text()
    assert result["superseded"] == "a-family-fresh"
    assert text.count("Status:** superseded") == 1
    assert current_decision(decisions)["direction"] == "c-japanese-precision"


def test_an_unknown_direction_is_refused(paths):
    decisions, manifest = paths

    with pytest.raises(DecisionError, match="unknown direction"):
        record_decision(decisions, manifest, "z-other", REASON)
    assert not decisions.exists()


def test_a_short_reason_is_refused(paths):
    decisions, manifest = paths

    with pytest.raises(DecisionError, match="reason"):
        record_decision(decisions, manifest, "a-family-fresh", "ok")


def test_choosing_the_current_direction_again_is_refused(paths):
    decisions, manifest = paths
    record_decision(decisions, manifest, "a-family-fresh", REASON)

    with pytest.raises(DecisionError, match="already"):
        record_decision(decisions, manifest, "a-family-fresh", REASON)


def test_no_decision_file_means_no_current_decision(tmp_path):
    assert current_decision(tmp_path / "missing.md") is None
