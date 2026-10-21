import json

import pytest
from fastapi.testclient import TestClient

import main
from design_decision import api

REASON = "Matches the family packs and stays readable for buyers."


@pytest.fixture
def client(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"directions": [{"id": "a-family-fresh", "label": "A · Family fresh"},
                                                   {"id": "b-clean-eco", "label": "B · Clean eco"}]}))
    lysstack = tmp_path / "LysStack"
    (lysstack / "projects" / "unigreen").mkdir(parents=True)
    monkeypatch.setattr(api, "MANIFEST", manifest)
    monkeypatch.setenv("HERMES_LYSSTACK_ROOT", str(lysstack))
    return TestClient(main.app), lysstack / "projects" / "unigreen" / "decisions.md"


def test_no_choice_yet_and_the_directions_are_listed(client):
    http, _ = client

    body = http.get("/design/unigreen/decision").json()

    assert body["decision"] is None
    assert [d["id"] for d in body["directions"]] == ["a-family-fresh", "b-clean-eco"]


def test_a_choice_is_recorded_and_then_read_back(client):
    http, decisions = client

    response = http.post("/design/unigreen/decision", json={"direction": "b-clean-eco", "reason": REASON})

    assert response.status_code == 201
    assert decisions.exists() and "Decision: Design direction — B · Clean eco" in decisions.read_text()
    assert http.get("/design/unigreen/decision").json()["decision"]["direction"] == "b-clean-eco"


def test_an_unknown_direction_or_short_reason_is_a_client_error(client):
    http, _ = client

    assert http.post("/design/unigreen/decision", json={"direction": "z", "reason": REASON}).status_code == 400
    assert http.post("/design/unigreen/decision", json={"direction": "a-family-fresh", "reason": "short"}).status_code == 422
