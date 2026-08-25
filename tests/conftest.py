import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

RUNNER_DIR = ROOT_DIR / "runner"
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))


def pytest_configure(config):
    config.addinivalue_line("markers", "live_agents: opt-in live execution tests for local agent CLIs")
