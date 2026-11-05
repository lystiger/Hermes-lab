from runtime.hermes_adapter import HermesActorAdapter
from runtime.observations import ObservationRegistry
from runtime.task_graph import TaskNode


def test_a_task_does_not_see_observations_from_another_job_with_the_same_task_id():
    reg = ObservationRegistry()
    reg.add_observation(job_id="job_dry", task_id="t1_fix", kind="discovery",
                        content="Task t1_fix completed dry-run execution by antigravity")
    reg.add_observation(job_id="job_real", task_id="t1_fix", kind="discovery", content="own retry note")
    reg.add_observation(job_id="job_dry", task_id="t0_dep", kind="discovery", content="other job dependency")

    task = TaskNode(task_id="t1_fix", job_id="job_real", dependencies=["t0_dep"])
    contents = [o.content for o in HermesActorAdapter._prior_observations(task, reg)]

    assert contents == ["own retry note"]
