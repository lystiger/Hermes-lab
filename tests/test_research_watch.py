import json

import pytest

from research import watch
from research.watch import Budget, ResearchError, bump_kind, dependency_findings, run, source_findings


def test_a_host_off_the_allowlist_is_refused_before_any_request(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("no request may be made to a host off the allowlist")

    monkeypatch.setattr(watch, "checked_urlopen", boom)

    with pytest.raises(ResearchError, match="allowlist"):
        watch.fetch_json("https://example.com/page", Budget())


def test_the_budget_stops_further_requests(monkeypatch):
    monkeypatch.setattr(watch, "checked_urlopen", lambda *a, **k: _Reply(b"{}"))
    budget = Budget(1)

    watch.fetch_json("https://pypi.org/pypi/x/json", budget)
    with pytest.raises(ResearchError, match="budget"):
        watch.fetch_json("https://pypi.org/pypi/y/json", budget)


class _Reply:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


@pytest.mark.parametrize("installed, latest, kind", [
    ("1.2.3", "2.0.0", "major"),
    ("1.2.3", "1.3.0", "minor"),
    ("1.2.3", "1.2.9", "patch"),
    ("1.2.3", "1.2.3", "none"),
    ("1.2.3", "not-a-version", "unknown"),
])
def test_bump_kind_reads_the_size_of_a_change(installed, latest, kind):
    assert bump_kind(installed, latest) == kind


def test_dependencies_report_installed_against_latest(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("pytest\n# a comment\n")
    fake = lambda url, budget: {"info": {"version": "999.0.0", "project_urls": {"Changelog": "https://example.com/c"}}}

    findings = dependency_findings(requirements, Budget(5), fetch=fake)

    assert len(findings) == 1
    assert findings[0]["package"] == "pytest" and findings[0]["bump"] == "major"
    assert findings[0]["notes_page"] == "https://example.com/c" and findings[0]["status"] == "FINDING"


def test_a_source_is_recorded_then_reports_only_real_changes(tmp_path):
    values = iter(["v1.0", "v1.0", "v1.1"])
    fake = lambda url, budget: {"tag_name": next(values)}
    sources = [{"name": "demo", "project": "unigreen", "url": "https://api.github.com/x", "field": "tag_name"}]

    first = source_findings(sources, tmp_path, Budget(10), fetch=fake)
    second = source_findings(sources, tmp_path, Budget(10), fetch=fake)
    third = source_findings(sources, tmp_path, Budget(10), fetch=fake)

    assert first[0]["status"] == "RECORDED"
    assert second[0]["status"] == "UNCHANGED"
    assert third[0]["status"] == "CHANGED" and third[0]["previous"] == "v1.0"
    assert json.loads((tmp_path / "demo.json").read_text())["value"] == "v1.1"


def test_a_failed_source_is_unproven_not_silently_dropped(tmp_path):
    def failing(url, budget):
        raise ResearchError("host 'x' is not on the research allowlist")

    findings = source_findings([{"name": "bad", "url": "https://x.example/", "field": "a"}], tmp_path, Budget(5), fetch=failing)

    assert findings[0]["status"] == "UNPROVEN"


def test_a_full_run_stays_within_its_budget(tmp_path, monkeypatch):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("pytest\nfastapi\n")
    sources = tmp_path / "sources.json"
    sources.write_text(json.dumps([{"name": "s", "url": "https://api.github.com/x", "field": "tag_name"}]))
    calls = []

    def fake_fetch(url, budget):
        budget.spend()
        calls.append(url)
        return {"info": {"version": "1.0"}} if "pypi" in url else {"tag_name": "v1"}

    monkeypatch.setattr(watch, "fetch_json", fake_fetch)
    result = run(requirements, sources, tmp_path / "state", budget_limit=10, fetch=fake_fetch)

    assert result["requests_used"] == len(calls) <= 10
    assert "nothing is installed or changed" in result["note"]


def test_the_researcher_profile_is_read_only_and_names_its_hosts():
    from pathlib import Path

    roles = json.loads((Path(__file__).resolve().parent.parent / "config" / "roles.json").read_text())

    assert roles["researcher"]["may_edit_product_source"] is False
    assert roles["researcher"]["network_hosts"] == sorted(watch.ALLOWED_HOSTS)
