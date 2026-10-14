import os
import sys
import tempfile
from pathlib import Path

import pytest

# Session-wide isolation, set before ANY test code runs (including unittest setUpClass, which runs
# before function-scoped fixtures and once started a real API server against the user's state dir).
# Per-test fixtures below still give each test its own fresh directories.
_SESSION_STATE = Path(tempfile.mkdtemp(prefix="hermes-test-state-"))
os.environ["HERMES_OPENRIG_LEDGER_DIR"] = str(_SESSION_STATE / "openrig-ledger")
os.environ["OPENRIG_HOME"] = str(_SESSION_STATE / "openrig-home")
os.environ["HERMES_EXECUTION_STATE"] = str(_SESSION_STATE / "execution-registry.json")

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
    # Never touch the real persisted Execution page state.
    monkeypatch.setenv("HERMES_EXECUTION_STATE", str(tmp_path_factory.mktemp("exec-state") / "registry.json"))
