import json

import pytest

from release.gate import classify, load_evidence, main, readiness

GOOD = {
    "tests": {"passed": 120, "failed": 0, "errors": 0},
    "security": {"verdict": "PASS"},
    "staging_flows": {"total": 160, "failed": 0},
}


@pytest.mark.parametrize("files, tier", [
    (["docs/notes.md", "README.md"], "skip"),
    (["frontend/app/[locale]/inquiry/page.tsx"], "full"),
    (["backend/src/unigreen/inquiries/models.py"], "full"),
    (["backend/migrations/versions/0042_add_column.py"], "full"),
    (["tests/test_thing.py", "scripts/helper.py"], "smoke"),
    (["runner/backends/thing.py"], "smoke"),
    (["config/unknown.yaml"], "full"),
    ([], "smoke"),
])
def test_the_tier_follows_what_the_change_touches(files, tier):
    assert classify(files) == tier


def test_everything_passing_is_ready():
    result = readiness("full", GOOD)

    assert result["verdict"] == "PASS" and result["blocked_by"] == []


def test_a_failing_flow_blocks_the_release_and_says_why():
    result = readiness("full", {**GOOD, "staging_flows": {"total": 160, "failed": 3}})

    assert result["verdict"] == "FAIL"
    assert result["blocked_by"] == ["staging_flows"]


def test_a_missing_check_is_unproven_not_a_pass():
    result = readiness("full", {"tests": GOOD["tests"], "security": GOOD["security"]})

    assert result["verdict"] == "UNPROVEN"
    assert [c["check"] for c in result["checks"] if c["status"] == "UNPROVEN"] == ["staging_flows"]


def test_no_passing_tests_is_a_failure_not_a_pass():
    result = readiness("smoke", {"tests": {"passed": 0, "failed": 0}, "security": {"verdict": "PASS"}})

    assert result["verdict"] == "FAIL"


def test_a_security_failure_blocks_even_a_smoke_change():
    result = readiness("smoke", {**GOOD, "security": {"verdict": "FAIL"}})

    assert result["verdict"] == "FAIL" and result["blocked_by"] == ["security"]


def test_a_docs_only_change_needs_no_trial():
    assert readiness("skip", {})["verdict"] == "PASS"


def test_a_flow_run_with_no_checks_is_unproven():
    result = readiness("full", {**GOOD, "staging_flows": {"total": 0, "failed": 0}})

    assert result["verdict"] == "UNPROVEN"


def test_an_unknown_tier_is_refused():
    with pytest.raises(ValueError):
        readiness("prod-now", GOOD)


def test_the_command_reads_evidence_and_exits_nonzero_on_failure(tmp_path, capsys):
    (tmp_path / "tests.json").write_text(json.dumps(GOOD["tests"]))
    (tmp_path / "security.json").write_text(json.dumps({"verdict": "FAIL"}))
    (tmp_path / "staging-flows.json").write_text(json.dumps(GOOD["staging_flows"]))

    code = main(["--evidence", str(tmp_path), "--files", "backend/src/x/models.py"])

    assert code == 1
    assert json.loads(capsys.readouterr().out)["verdict"] == "FAIL"
    assert load_evidence(tmp_path)["security"] == {"verdict": "FAIL"}


def test_the_production_role_can_never_deploy():
    from pathlib import Path

    roles = json.loads((Path(__file__).resolve().parent.parent / "config" / "roles.json").read_text())

    assert roles["production"]["may_deploy_to_production"] is False
    assert roles["production"]["network"] is False
