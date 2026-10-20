import json
from datetime import datetime, timezone

from runtime.usage_limits import load_agent_limits

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def _load(tmp_path, records):
    for name, record in records.items():
        text = record if isinstance(record, str) else json.dumps(record)
        (tmp_path / name).write_text(text)
    return {a["id"]: a for a in load_agent_limits(tmp_path, NOW)}


def _record(**extra):
    base = {"id": "a", "ready": True, "updatedAt": "2026-10-20T11:59:00Z"}
    base.update(extra)
    return base


def test_fullest_window_decides_headline_and_reset(tmp_path):
    agents = _load(tmp_path, {"a.json": _record(limits=[
        {"label": "5h", "percent": 0.20, "resetsAt": "2026-10-20T13:00:00Z"},
        {"label": "Weekly", "percent": 0.80, "resetsAt": "2026-10-25T00:00:00Z"},
    ])})
    a = agents["a"]
    assert (a["usedPct"], a["leftPct"], a["status"]) == (80, 20, "warn")
    assert a["resetsAt"] == "2026-10-25T00:00:00Z"


def test_threshold_uses_unrounded_percent(tmp_path):
    agents = _load(tmp_path, {
        "a.json": _record(id="a", limits=[{"label": "x", "percent": 0.746}]),
        "b.json": _record(id="b", limits=[{"label": "x", "percent": 0.75}]),
        "c.json": _record(id="c", limits=[{"label": "x", "percent": 0.899}]),
        "d.json": _record(id="d", limits=[{"label": "x", "percent": 0.90}]),
    })
    assert [agents[k]["status"] for k in "abcd"] == ["ok", "warn", "warn", "alarm"]


def test_balance_left_and_status(tmp_path):
    agents = _load(tmp_path, {"a.json": _record(balance={"funded": 20, "remaining": 1.5, "spent": 18.5, "currency": "USD"})})
    a = agents["a"]
    assert a["leftPct"] == 8 and a["status"] == "alarm"
    assert a["balance"] == {"funded": 20.0, "remaining": 1.5, "spent": 18.5, "currency": "USD"}


def test_past_reset_is_not_shown(tmp_path):
    agents = _load(tmp_path, {"a.json": _record(limits=[{"label": "x", "percent": 0.5, "resetsAt": "2026-10-20T11:00:00Z"}])})
    a = agents["a"]
    assert a["resetsAt"] is None and a["windows"][0]["resetsAt"] is None


def test_corrupt_records_and_dotfiles_do_not_break_response(tmp_path):
    agents = _load(tmp_path, {
        "good.json": _record(id="good", limits=[{"label": "x", "percent": 0.1}]),
        "bad.json": "{not json",
        "list.json": "[1]",
        ".hidden.json": "{}",
        ".tmp123": "",
        "weird.json": {"id": 5, "name": {"x": 1}, "ready": "yes", "limits": [None, {"label": [1], "percent": "nan", "resetsAt": "0001-01-01T00:00:00+05:00"}],
                       "balance": {"funded": "nan", "remaining": "inf", "secret": "sk-123", "path": "/home/u"}, "authHelpText": 7},
    })
    assert set(agents) == {"good", "bad", "list", "weird"}
    assert agents["bad"]["ready"] is False
    weird = agents["weird"]
    assert weird["ready"] is False and weird["authHelp"] == ""
    json.dumps(list(agents.values()), allow_nan=False)  # must be serialisable
    assert "sk-123" not in json.dumps(weird) and "/home/u" not in json.dumps(weird)
