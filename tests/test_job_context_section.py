import pytest
from pathlib import Path
from runtime.hermes_adapter import HermesActorAdapter
from runtime.task_graph import TaskNode, TaskStatus


def test_goal_truncation_under_limit():
    """Goal with <= 600 characters is preserved without truncation or ellipsis."""
    goal = "Fix the login authentication bug and ensure all unit tests pass."
    assert len(goal) <= 600
    truncated = HermesActorAdapter.truncate_goal(goal, limit=600)
    assert truncated == goal
    assert not truncated.endswith("…")


def test_goal_truncation_over_limit_word_boundary():
    """Goal with > 600 characters is cut at word boundary with '…' and length <= 601."""
    # Construct a goal of 150 words (~750 chars)
    words = [f"word{i:03d}" for i in range(150)]
    goal = " ".join(words)
    assert len(goal) > 600

    truncated = HermesActorAdapter.truncate_goal(goal, limit=600)
    assert truncated.endswith("…")
    # Content before ellipsis must be at most 600 characters
    content_before = truncated[:-1]
    assert len(content_before) <= 600
    # Must cut at word boundary: the last word before ellipsis must be a full word, not cut
    last_word = content_before.split()[-1]
    assert last_word.startswith("word")
    assert len(last_word) == 7  # wordXXX is 7 characters


def test_goal_truncation_exact_limit():
    """Goal with exactly 600 characters is preserved as-is without ellipsis."""
    # 100 words of 5 chars each plus space = 600 chars without trailing space
    words = ["hello"] * 100
    goal = " ".join(words)
    assert len(goal) == 599
    goal += "!"
    assert len(goal) == 600

    truncated = HermesActorAdapter.truncate_goal(goal, limit=600)
    assert truncated == goal
    assert not truncated.endswith("…")


def test_sibling_listing_and_format():
    """Sibling tasks are listed in the form <task_id>: <first sentence, <= 160 chars> (<status>)."""
    t1 = TaskNode(
        task_id="t1_auth",
        description="Implement user authentication module. Ensure JWT tokens are verified.",
        status=TaskStatus.SUCCEEDED,
    )
    t2 = TaskNode(
        task_id="t2_rate",
        description="Add rate limiting to all public endpoints. Prevent abuse.",
        status=TaskStatus.RUNNING,
    )
    t3 = TaskNode(
        task_id="t3_verify",
        description="Verify security and rate limiting against attack vectors.",
        status=TaskStatus.PENDING,
    )
    t4 = TaskNode(
        task_id="t4_cleanup",
        description="Clean up temporary files and logs.",
        status=TaskStatus.FAILED,
    )

    current_task = TaskNode(task_id="t0_init", description="Initialize project.")

    adapter = HermesActorAdapter()
    sec = adapter.build_job_context_section(
        task=current_task,
        goal="Build secure API endpoints.",
        tasks=[t1, t2, t3, t4],
    )

    assert "--- JOB CONTEXT ---" in sec
    assert "--- END JOB CONTEXT ---" in sec
    assert "Build secure API endpoints." in sec

    # Sibling tasks listed with status
    assert "t1_auth: Implement user authentication module. (done)" in sec
    assert "t2_rate: Add rate limiting to all public endpoints. (running)" in sec
    assert "t3_verify: Verify security and rate limiting against attack vectors. (pending)" in sec
    assert "t4_cleanup: Clean up temporary files and logs. (failed)" in sec


def test_self_exclusion():
    """The current task is not listed in the sibling tasks."""
    t1 = TaskNode(task_id="t1_auth", description="Implement auth.", status=TaskStatus.SUCCEEDED)
    t2 = TaskNode(task_id="t2_rate", description="Implement rate limit.", status=TaskStatus.RUNNING)
    t3 = TaskNode(task_id="t3_verify", description="Verify everything.", status=TaskStatus.PENDING)

    adapter = HermesActorAdapter()
    # When t2 is current task:
    sec = adapter.build_job_context_section(
        task=t2,
        goal="Build secure API.",
        tasks=[t1, t2, t3],
    )

    assert "t1_auth: Implement auth. (done)" in sec
    assert "t3_verify: Verify everything. (pending)" in sec
    # Current task t2 must NOT be listed
    assert "t2_rate" not in sec


def test_first_sentence_and_max_160_chars():
    """First sentence of description is extracted and capped at 160 characters."""
    # Multi-sentence
    desc_multi = "First sentence here. Second sentence here. Third sentence here."
    t1 = TaskNode(task_id="t1", description=desc_multi, status=TaskStatus.PENDING)

    # Long sentence > 160 characters
    long_first = "A" * 200 + ". Second sentence."
    t2 = TaskNode(task_id="t2", description=long_first, status=TaskStatus.PENDING)

    adapter = HermesActorAdapter()
    sec = adapter.build_job_context_section(
        task=TaskNode(task_id="t0", description="Self"),
        goal="Goal",
        tasks=[t1, t2],
    )

    assert "t1: First sentence here. (pending)" in sec
    # t2 must be at most 160 characters for the sentence part
    assert f"t2: {'A' * 160} (pending)" in sec
    assert "Second sentence" not in sec


def test_status_mapping():
    """Status mapping covers pending, running, done, and failed."""
    assert HermesActorAdapter.normalize_task_status(TaskStatus.SUCCEEDED) == "done"
    assert HermesActorAdapter.normalize_task_status("succeeded") == "done"
    assert HermesActorAdapter.normalize_task_status("done") == "done"

    assert HermesActorAdapter.normalize_task_status(TaskStatus.RUNNING) == "running"
    assert HermesActorAdapter.normalize_task_status("running") == "running"

    assert HermesActorAdapter.normalize_task_status(TaskStatus.FAILED) == "failed"
    assert HermesActorAdapter.normalize_task_status(TaskStatus.CANCELLED) == "failed"
    assert HermesActorAdapter.normalize_task_status("failed") == "failed"
    assert HermesActorAdapter.normalize_task_status("cancelled") == "failed"

    assert HermesActorAdapter.normalize_task_status(TaskStatus.PENDING) == "pending"
    assert HermesActorAdapter.normalize_task_status(TaskStatus.READY) == "pending"
    assert HermesActorAdapter.normalize_task_status(TaskStatus.BLOCKED) == "pending"
    assert HermesActorAdapter.normalize_task_status("pending") == "pending"


def test_prompt_opens_with_job_context_section():
    """Effective prompt opens with the job context section."""
    t1 = TaskNode(task_id="t1", description="Sibling task.", status=TaskStatus.SUCCEEDED)
    t2 = TaskNode(task_id="t2", description="Current task.", status=TaskStatus.RUNNING)

    adapter = HermesActorAdapter()
    prompt = adapter.build_effective_prompt(
        base_prompt="Do current task.",
        task=t2,
        job_goal="Achieve 100% test coverage across all modules.",
        tasks=[t1, t2],
    )

    # Prompt must open with the job context section
    assert prompt.startswith("--- JOB CONTEXT ---")
    assert "--- END JOB CONTEXT ---" in prompt
    assert "Achieve 100% test coverage across all modules." in prompt
    assert "t1: Sibling task. (done)" in prompt
    assert "t2" not in prompt[:prompt.index("Do current task.")]
    # Task role section comes after job context section
    assert prompt.index("--- JOB CONTEXT ---") < prompt.index("--- HERMES TASK ROLE ---")


def test_prompt_omits_job_context_when_no_goal_and_no_tasks():
    """Job context section is omitted when there is no goal and no sibling tasks."""
    adapter = HermesActorAdapter()
    task = TaskNode(task_id="t1", description="Lone task without job context.")
    prompt = adapter.build_effective_prompt(
        base_prompt="Do lone task.",
        task=task,
    )

    assert "--- JOB CONTEXT ---" not in prompt
    assert "--- END JOB CONTEXT ---" not in prompt


def test_budget_bound_9_tasks_2000_char_goal():
    """
    Budget constraint: for a job with 9 tasks and 2,000-character goal,
    the job section adds at most 2,500 characters to the prompt.
    """
    long_goal = ("Optimize database query performance and cache layer. " * 40).strip()
    assert len(long_goal) >= 2000

    tasks = [
        TaskNode(
            task_id=f"t{i}_subtask",
            description=f"Subtask {i} description detailing performance optimization for module {i}. Extra details.",
            status=TaskStatus.PENDING if i > 3 else (TaskStatus.RUNNING if i == 3 else TaskStatus.SUCCEEDED),
        )
        for i in range(9)
    ]

    current_task = tasks[0]

    adapter = HermesActorAdapter()

    # Prompt without job context
    prompt_before = adapter.build_effective_prompt(
        base_prompt="Implement task 0.",
        task=current_task,
    )

    # Prompt with job context
    prompt_after = adapter.build_effective_prompt(
        base_prompt="Implement task 0.",
        task=current_task,
        job_goal=long_goal,
        tasks=tasks,
    )

    added_chars = len(prompt_after) - len(prompt_before)
    assert added_chars <= 2500, f"Added {added_chars} chars, exceeding 2500 char budget"
    # Ensure all 8 sibling tasks are in the prompt
    for i in range(1, 9):
        assert f"t{i}_subtask:" in prompt_after
    # Ensure current task is excluded from sibling list
    assert "t0_subtask:" not in prompt_after


def test_prepare_effective_prompt_resolves_context_engine():
    """_prepare_effective_prompt automatically extracts goal and tasks from engine in context."""
    from unittest.mock import MagicMock

    mock_engine = MagicMock()
    mock_engine.job.goal = "Build user dashboard."
    
    t1 = TaskNode(task_id="t1", description="Build API.", status=TaskStatus.SUCCEEDED)
    t2 = TaskNode(task_id="t2", description="Build UI.", status=TaskStatus.RUNNING)
    mock_engine.graph.list_tasks.return_value = [t1, t2]

    adapter = HermesActorAdapter()
    prompt = adapter._prepare_effective_prompt(
        task=t2,
        actor_id="antigravity",
        role="builder",
        context={"engine": mock_engine},
    )

    assert prompt.startswith("--- JOB CONTEXT ---")
    assert "Build user dashboard." in prompt
    assert "t1: Build API. (done)" in prompt
    assert "t2" not in prompt[:prompt.index("Build UI.")]


def test_prepare_effective_prompt_resolves_context_job_dict():
    """_prepare_effective_prompt extracts goal from context['job']['goal']."""
    adapter = HermesActorAdapter()
    t = TaskNode(task_id="t1", description="Independent task.")
    prompt = adapter._prepare_effective_prompt(
        task=t,
        actor_id="antigravity",
        role="builder",
        context={"job": {"goal": "Standalone goal."}},
    )

    assert prompt.startswith("--- JOB CONTEXT ---")
    assert "Standalone goal." in prompt


def test_dict_tasks_and_markdown_headings():
    """Handles tasks passed as dicts and descriptions with markdown headings."""
    dict_tasks = [
        {"task_id": "d1", "description": "# Main Setup\nInitialize database. Add tables.", "status": "succeeded"},
        {"task_id": "d2", "description": "", "status": "pending"},
    ]
    adapter = HermesActorAdapter()
    sec = adapter._job_context_section(
        task={"task_id": "curr"},
        goal="Dict tasks goal",
        tasks=dict_tasks,
    )

    assert "d1: Initialize database. (done)" in sec
    assert "d2: (pending)" in sec

