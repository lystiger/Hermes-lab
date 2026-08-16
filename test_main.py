from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready():
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_version():
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {"version": "0.1.0"}


def test_info():
    response = client.get("/info")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Hermes Lab"
    assert data["version"] == "0.1.0"
    assert data["environment"] == "development"


def test_metrics():
    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "uptime_seconds" in data
    assert "requests_handled" in data
    assert isinstance(data["uptime_seconds"], int)
    assert isinstance(data["requests_handled"], int)
    assert data["uptime_seconds"] >= 0
    assert data["requests_handled"] >= 0
    assert data == {"uptime_seconds": 0, "requests_handled": 0}
