from personas.agent_state_reducer import AgentStateReducer


class FakeAgentService:
    def __init__(self):
        self.status = {}

    def set_agent_status(self, agent_id, status, current_task=None):
        self.status[agent_id] = (status, current_task)


def make():
    service = FakeAgentService()
    return AgentStateReducer(service), service


def phase(reducer, kind, name, order, agent="claude"):
    reducer.apply(agent, kind, "", {"phase": name, "order": order, "role": "hardener"}, job_id="job-1")


def test_phase_events_drive_agent_status():
    reducer, service = make()
    phase(reducer, "phase.started", "harden", 2)
    assert service.status["claude"] == ("RUNNING", "harden")
    phase(reducer, "phase.completed", "harden", 2)
    assert service.status["claude"] == ("IDLE", None)


def test_agent_stays_running_until_every_parallel_phase_finishes():
    reducer, service = make()
    phase(reducer, "phase.started", "backend", 2)
    phase(reducer, "phase.started", "frontend", 3)
    phase(reducer, "phase.completed", "backend", 2)
    assert service.status["claude"] == ("RUNNING", "frontend")
    phase(reducer, "phase.completed", "frontend", 3)
    assert service.status["claude"] == ("IDLE", None)


def test_agent_finished_inside_a_phase_does_not_go_idle_early():
    reducer, service = make()
    phase(reducer, "phase.started", "build", 1)
    reducer.apply("claude", "agent.finished", "", {})
    assert service.status["claude"][0] == "RUNNING"


def test_failed_phase_and_timeout_are_errors_and_cancel_is_idle():
    reducer, service = make()
    phase(reducer, "phase.started", "build", 1)
    phase(reducer, "phase.failed", "build", 1)
    assert service.status["claude"] == ("ERROR", None)

    reducer.apply("codex", "agent.started", "", {"task": "t"})
    reducer.apply("codex", "agent.timed_out", "", {})
    assert service.status["codex"] == ("ERROR", None)

    phase(reducer, "phase.started", "verify", 4, agent="gemini")
    reducer.apply("gemini", "agent.cancelled", "", {})
    assert service.status["gemini"] == ("IDLE", None)
