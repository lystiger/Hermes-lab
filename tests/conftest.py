import asyncio
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
# Never post test events to a live Hermes API inherited from the developer's shell. Tests that need a
# control URL (e.g. the cross-process a2a smoke test) start their own server and pass it explicitly.
os.environ.pop("LYSSTACK_CONTROL_URL", None)
os.environ["HERMES_AGENT_MODELS"] = str(_SESSION_STATE / "agent_models.json")
# The API resumes interrupted jobs on startup; a test app must not pick up other tests' jobs.
os.environ["HERMES_AUTO_RESUME"] = "0"
# The console lists jobs from the runs folder; test jobs (including those written by API
# subprocesses, which inherit this) must never land in the real one.
os.environ["HERMES_RUNS_ROOT"] = str(_SESSION_STATE / "hermes-runs")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("HERMES_DATABASE_URL", None)

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

RUNNER_DIR = ROOT_DIR / "runner"
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))


def pytest_configure(config):
    config.addinivalue_line("markers", "live_agents: opt-in live execution tests for local agent CLIs")


class _TimerWakeSelector:
    """Caps every selector wait at one tick.

    Under a sandbox that denies socket writes, asyncio drops the wakeup a worker thread sends to
    its loop, so the loop can sleep forever. Waking on a timer bounds that stall to one tick.
    """

    def __init__(self, selector):
        self._selector = selector

    def select(self, timeout=None):
        if timeout is None or timeout > 0.01:
            timeout = 0.01
        return self._selector.select(timeout)

    def __getattr__(self, name):
        return getattr(self._selector, name)


class _TimerWakePolicy(asyncio.DefaultEventLoopPolicy):
    def new_event_loop(self):
        loop = super().new_event_loop()
        loop._selector = _TimerWakeSelector(loop._selector)
        return loop


asyncio.set_event_loop_policy(_TimerWakePolicy())


@pytest.fixture(autouse=True)
def _isolated_openrig_ledger(tmp_path_factory, monkeypatch):
    # Every test gets its own OpenRig ownership ledger, so no test writes to the real user state dir.
    monkeypatch.setenv("HERMES_OPENRIG_LEDGER_DIR", str(tmp_path_factory.mktemp("openrig-ledger")))
    # No daemon.json here: a test can never reach the real OpenRig daemon's teardown API.
    monkeypatch.setenv("OPENRIG_HOME", str(tmp_path_factory.mktemp("openrig-home")))
    # Never touch the real persisted Execution page state.
    monkeypatch.setenv("HERMES_EXECUTION_STATE", str(tmp_path_factory.mktemp("exec-state") / "registry.json"))


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path_factory, monkeypatch):
    # Path.home() drives the agent settings (~/.gemini) and default run folders (~/hermes-runs).
    # A per-test home keeps them out of the real account, and out of reach of a read-only sandbox.
    # It sits beside tmp_path, not inside it, so a test that checks tmp_path stays empty.
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))


@pytest.fixture(autouse=True)
def _isolated_job_runs(tmp_path, monkeypatch):
    # The job service is a process-wide singleton. Without this, tests persist their jobs into the
    # live repo's hermes-runs folder, where the running API reloads them on restart.
    from jobs.job_service import job_service
    monkeypatch.setattr(job_service, "runs_root", tmp_path / "hermes-runs")


@pytest.fixture(autouse=True)
def _isolated_model_registry(tmp_path, monkeypatch):
    import agent_models
    monkeypatch.setenv("HERMES_CODEX_MODELS_CACHE", str(tmp_path / "models_cache.json"))
    monkeypatch.setattr(agent_models, "model_registry", agent_models.ModelRegistry(
        tmp_path / "agent_models.json", tmp_path / "codex.toml"))
