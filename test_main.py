import asyncio
import threading
import time

import httpx

from main import app


class ASGITestClient:
    @staticmethod
    def get(path):
        async def perform_request():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as async_client:
                return await async_client.get(path)

        return asyncio.run(perform_request())


client = ASGITestClient()


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


def test_metrics_uptime_nondecreasing():
    first = client.get("/metrics").json()["uptime_seconds"]
    time.sleep(1.1)
    second = client.get("/metrics").json()["uptime_seconds"]
    assert second >= first
    assert second > first


def test_metrics_requests_handled_includes_current_request():
    before = client.get("/metrics").json()["requests_handled"]
    after = client.get("/metrics").json()["requests_handled"]
    # Each /metrics call itself is counted, so the count strictly
    # increases between two consecutive calls.
    assert after == before + 1


def test_metrics_requests_handled_never_decreases_and_counts_all_requests():
    baseline = client.get("/metrics").json()["requests_handled"]
    client.get("/health")
    client.get("/version")
    client.get("/info")
    client.get("/ready")
    after = client.get("/metrics").json()["requests_handled"]
    # baseline call + 4 other requests + this /metrics call = +5
    assert after == baseline + 5


def test_metrics_requests_handled_concurrency_safe():
    baseline = client.get("/metrics").json()["requests_handled"]

    num_threads = 20
    calls_per_thread = 10

    def hammer():
        for _ in range(calls_per_thread):
            client.get("/health")

    threads = [threading.Thread(target=hammer) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    after = client.get("/metrics").json()["requests_handled"]
    expected = baseline + (num_threads * calls_per_thread) + 1
    assert after == expected
