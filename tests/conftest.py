import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

RUNNER_DIR = ROOT_DIR / "runner"
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))


def pytest_configure(config):
    config.addinivalue_line("markers", "live_agents: opt-in live execution tests for local agent CLIs")


@pytest.fixture(autouse=True)
def _isolated_openrig_ledger(tmp_path_factory, monkeypatch):
    # Every test gets its own OpenRig ownership ledger, so no test writes to the real user state dir.
    monkeypatch.setenv("HERMES_OPENRIG_LEDGER_DIR", str(tmp_path_factory.mktemp("openrig-ledger")))
    # No daemon.json here: a test can never reach the real OpenRig daemon's teardown API.
    monkeypatch.setenv("OPENRIG_HOME", str(tmp_path_factory.mktemp("openrig-home")))
