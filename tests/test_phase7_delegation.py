import importlib.util
import json
import os
import sys
import tempfile
import unittest
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

RUNNER_DIR = ROOT_DIR / "runner"
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

def _get_runner_module():
    runner_path = RUNNER_DIR / "run-hermes-sprint.py"
    spec = importlib.util.spec_from_file_location("run_hermes_sprint", str(runner_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

from capabilities import (
    Capability,
    CapabilityRef,
    CapabilityRegistry,
    DEFAULT_CAPABILITY_PROFILES,
    create_default_capability_registry,
)
from delegation import (
    DelegationRequest,
    DelegationDecision,
    TaskAssignment,
    LYSSTACK_DELEGATION_START,
    LYSSTACK_DELEGATION_END,
)
from tools import (
    ToolProfile,
    ToolInvocationRequest,
    ToolInvocationResult,
    ToolRegistry,
    default_tool_registry,
    LYSSTACK_TOOL_REQUEST_START,
    LYSSTACK_TOOL_REQUEST_END,
)
from subagents import SubagentProfile, SubagentManager
from a2a import A2AOutput, AgentTurnResult, parse_a2a_output, LYSSTACK_A2A_START, LYSSTACK_A2A_END
from persona import AgentProfile, resolve_agent_profile
from runner.backends.base import ExecutionResult


class TestPhase7CapabilityRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = CapabilityRegistry()
        self.gemini = AgentProfile(id="gemini", displayName="Gemini", capabilities=["code.python", "backend.fastapi", "testing.unit"])
        self.claude = AgentProfile(id="claude", displayName="Claude", capabilities=["review.code", "review.concurrency", "code.python"])
        self.codex = AgentProfile(id="codex", displayName="Codex", capabilities=["verification", "testing.integration", "git.inspect"])

        self.registry.register_actor(self.gemini)
        self.registry.register_actor(self.claude)
        self.registry.register_actor(self.codex)

    def test_open_string_capabilities_registered(self):
        cap = self.registry.register_capability("custom.domain.specific.capability")
        self.assertEqual(cap.id, "custom.domain.specific.capability")

    def test_actor_satisfies_capabilities(self):
        self.assertTrue(self.registry.actor_satisfies("claude", ["review.code", "review.concurrency"]))
        self.assertFalse(self.registry.actor_satisfies("gemini", ["review.concurrency"]))
        self.assertTrue(self.registry.actor_satisfies("gemini", ["code.python"]))

    def test_find_actors_and_deterministic_selection(self):
        # Request requiring review.code and review.concurrency -> ONLY Claude satisfies both
        decision = self.registry.select_actor(required_capabilities=["review.code", "review.concurrency"])
        self.assertEqual(decision.status, "selected")
        self.assertEqual(decision.selectedActorId, "claude")
        self.assertIn("review.code", decision.matchedCapabilities)
        self.assertIn("review.concurrency", decision.matchedCapabilities)

    def test_preferred_actor_boost(self):
        # Both gemini and claude have code.python
        decision_default = self.registry.select_actor(required_capabilities=["code.python"])
        self.assertIn(decision_default.selectedActorId, ["claude", "gemini"])

        # Preferred claude
        decision_claude = self.registry.select_actor(required_capabilities=["code.python"], preferred_actors=["claude"])
        self.assertEqual(decision_claude.selectedActorId, "claude")

        # Preferred gemini
        decision_gemini = self.registry.select_actor(required_capabilities=["code.python"], preferred_actors=["gemini"])
        self.assertEqual(decision_gemini.selectedActorId, "gemini")

    def test_excluded_actor_filtered(self):
        # Both have code.python, but claude is excluded
        decision = self.registry.select_actor(required_capabilities=["code.python"], excluded_actors=["claude"])
        self.assertEqual(decision.selectedActorId, "gemini")

    def test_no_match_returns_deterministic_no_match_status(self):
        # No actor has quantum.cryptography
        decision = self.registry.select_actor(required_capabilities=["quantum.cryptography"])
        self.assertEqual(decision.status, "no_match")
        self.assertIsNone(decision.selectedActorId)
        self.assertIn("quantum.cryptography", decision.missingCapabilities)


class TestPhase7DelegationAndTaskExecutionIntegration(unittest.TestCase):
    """
    ABSOLUTE ACCEPTANCE TEST A:
    Gemini executes -> emits DelegationRequest(requiredCapabilities=["review.code", "review.concurrency"])
    -> CapabilityRegistry deterministically selects Claude
    -> Hermes records delegation decision & TaskAssignment
    -> LysStack message sent to Claude (kind="delegation", intent="task_request")
    -> Hermes schedules Claude
    -> Claude executes and emits task_result
    -> Hermes marks TaskAssignment completed!
    """

    def test_full_delegation_flow_gemini_to_claude(self):
        mod = _get_runner_module()
        HermesSprintRunner = mod.HermesSprintRunner

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            p1 = tmp_root / "p1.md"
            p1.write_text("Builder prompt", encoding="utf-8")
            p2 = tmp_root / "p2.md"
            p2.write_text("Hardener prompt", encoding="utf-8")

            spec_path = ROOT_DIR / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=False)
            runner.job_id = "job_delegation_test"
            runner.thread_id = "thread_job_delegation_test"
            runner.run_dir = tmp_root / "runs" / "test_del"
            runner.run_dir.mkdir(parents=True, exist_ok=True)
            runner.messages_file = runner.run_dir / "messages.jsonl"
            runner.worktree_root = tmp_root / "worktrees"
            (runner.worktree_root / "worker").mkdir(parents=True, exist_ok=True)

            phase1 = {"name": "01_builder", "role": "builder", "agent": "gemini", "worktree_dir": "worker", "prompt_file": str(p1)}
            phase2 = {"name": "02_hardener", "role": "hardener", "agent": "claude", "worktree_dir": "worker", "prompt_file": str(p2)}
            runner.spec["phases"] = [phase1, phase2]

            conv_id = "conv_delegation_flow"

            # 1. Seed initial message to trigger Gemini
            runner._record_message(
                from_actor={"id": "operator", "kind": "user", "displayName": "Operator"},
                to_actors=[{"id": "gemini", "kind": "agent", "displayName": "Gemini"}],
                kind="operator",
                intent="question",
                text="Please scaffold and delegate concurrency audit.",
                conversation_id=conv_id,
            )

            execution_log = []

            def stub_agent_execute(context):
                agent_name = context.phase["agent"]
                execution_log.append(agent_name)

                # Turn 1: Gemini produces a DelegationRequest requiring review.code & review.concurrency
                if agent_name == "gemini" and len(execution_log) == 1:
                    raw_stdout = f"""
Gemini Implementation Complete:
State store scaffolded. Requesting concurrency audit.

{LYSSTACK_DELEGATION_START}
{{
  "task": "Review scheduler mutex synchronization and deadlock risks",
  "requiredCapabilities": ["review.code", "review.concurrency"]
}}
{LYSSTACK_DELEGATION_END}
"""
                # Turn 2: Claude executes delegated task and returns structured task_result
                elif agent_name == "claude" and len(execution_log) == 2:
                    raw_stdout = f"""
Claude Concurrency Review:
Audited scheduler.py. Mutex locking verified clean.

{LYSSTACK_A2A_START}
{{
  "intent": "task_result",
  "to": ["gemini"],
  "text": "Concurrency audit passed. No race conditions detected.",
  "conversationId": "{conv_id}"
}}
{LYSSTACK_A2A_END}
"""
                else:
                    raw_stdout = "No further action."

                return ExecutionResult(command=[agent_name], returncode=0, stdout=raw_stdout, stderr="", backend="subprocess")

            mock_registry = MagicMock()
            mock_adapter = MagicMock()
            mock_adapter.execute.side_effect = stub_agent_execute
            mock_registry.get.return_value = mock_adapter
            runner.agent_registry = mock_registry

            # Run scheduler loop
            runner.schedule_a2a_turns(phase1, runner.worktree_root / "worker", conversation_id=conv_id)

            # Assert execution sequence: Gemini -> Claude
            self.assertEqual(len(execution_log), 2)
            self.assertEqual(execution_log[0], "gemini")
            self.assertEqual(execution_log[1], "claude")

            # Verify TaskAssignment was created and marked completed
            self.assertEqual(len(runner.task_assignments), 1)
            task_assignment = list(runner.task_assignments.values())[0]
            self.assertEqual(task_assignment.ownerActorId, "claude")
            self.assertEqual(task_assignment.delegatedBy, "gemini")
            self.assertEqual(task_assignment.status, "completed")
            self.assertIsNotNone(task_assignment.completedAt)

            # Verify recorded delegation message
            del_msg = next((m for m in runner.local_messages if m.get("kind") == "delegation"), None)
            self.assertIsNotNone(del_msg)
            self.assertEqual(del_msg["from"]["id"], "gemini")
            self.assertEqual(del_msg["to"][0]["id"], "claude")
            self.assertEqual(del_msg["intent"], "task_request")


class TestPhase7ToolExecutionIntegration(unittest.TestCase):
    """
    ABSOLUTE ACCEPTANCE TEST B:
    Claude emits ToolInvocationRequest(tool.git.inspect, operation="diff")
    -> Hermes validates permission
    -> ToolRegistry executes safe read-only git diff
    -> Structured ToolInvocationResult is recorded into LysStack
    -> Claude receives tool result in context
    """

    def test_tool_git_inspect_execution_and_result_delivery(self):
        mod = _get_runner_module()
        HermesSprintRunner = mod.HermesSprintRunner

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            target_repo = tmp_root / "repo"
            target_repo.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=target_repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=target_repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=target_repo, check=True)
            (target_repo / "feature.py").write_text("# initial version\n", encoding="utf-8")
            subprocess.run(["git", "add", "feature.py"], cwd=target_repo, check=True)
            subprocess.run(["git", "commit", "-m", "initial commit"], cwd=target_repo, check=True)

            # Modify feature.py in worktree
            (target_repo / "feature.py").write_text("# modified with mutex\n", encoding="utf-8")

            p2 = tmp_root / "p2.md"
            p2.write_text("Hardener prompt", encoding="utf-8")

            spec_path = ROOT_DIR / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=False)
            runner.job_id = "job_tool_test"
            runner.thread_id = "thread_job_tool_test"
            runner.run_dir = tmp_root / "runs" / "test_tool"
            runner.run_dir.mkdir(parents=True, exist_ok=True)
            runner.messages_file = runner.run_dir / "messages.jsonl"
            runner.worktree_root = tmp_root / "worktrees"
            (runner.worktree_root / "worker").mkdir(parents=True, exist_ok=True)

            phase = {"name": "02_hardener", "role": "hardener", "agent": "claude", "worktree_dir": target_repo.name, "prompt_file": str(p2)}
            runner.spec["phases"] = [phase]
            runner.worktree_root = target_repo.parent

            conv_id = "conv_tool_flow"
            runner._record_message(
                from_actor={"id": "operator", "kind": "user", "displayName": "Operator"},
                to_actors=[{"id": "claude", "kind": "agent", "displayName": "Claude"}],
                kind="operator",
                intent="question",
                text="Please inspect git diff.",
                conversation_id=conv_id,
            )

            # Claude emits tool request for tool.git.inspect
            def stub_claude_execute(context):
                raw_stdout = f"""
Claude analyzing code:
Requesting git diff via tool.

{LYSSTACK_TOOL_REQUEST_START}
{{
  "toolId": "tool.git.inspect",
  "args": {{
    "operation": "diff"
  }}
}}
{LYSSTACK_TOOL_REQUEST_END}
"""
                return ExecutionResult(command=["claude"], returncode=0, stdout=raw_stdout, stderr="", backend="subprocess")

            mock_registry = MagicMock()
            mock_adapter = MagicMock()
            mock_adapter.execute.side_effect = stub_claude_execute
            mock_registry.get.return_value = mock_adapter
            runner.agent_registry = mock_registry

            runner.schedule_a2a_turns(phase, target_repo, conversation_id=conv_id)

            # Verify tool_result message was recorded
            tool_msg = next((m for m in runner.local_messages if m.get("kind") == "tool_result"), None)
            self.assertIsNotNone(tool_msg)
            self.assertEqual(tool_msg["from"]["id"], "tool.git.inspect")
            self.assertEqual(tool_msg["from"]["kind"], "tool")
            self.assertEqual(tool_msg["to"][0]["id"], "claude")
            self.assertEqual(tool_msg["intent"], "tool_result")
            self.assertIn("modified with mutex", tool_msg["text"])

    def test_mutating_git_command_rejected_by_git_inspector(self):
        treq = ToolInvocationRequest(
            toolId="tool.git.inspect",
            args={"operation": "push"},  # Forbidden mutating operation
        )
        res = default_tool_registry.execute(treq)
        self.assertEqual(res.status, "rejected")
        self.assertIn("not permitted", res.error)

    def test_unregistered_tool_rejected(self):
        treq = ToolInvocationRequest(
            toolId="tool.arbitrary.malicious",
            args={"cmd": "rm -rf /"},
        )
        res = default_tool_registry.execute(treq)
        self.assertEqual(res.status, "rejected")
        self.assertIn("not registered", res.error)


class TestPhase7SubagentsBoundedManagement(unittest.TestCase):
    """
    ABSOLUTE ACCEPTANCE TEST C:
    Subagent creation is bounded, controller-owned, and uses the standard ActorRef/Message transport.
    """

    def test_subagent_manager_limits_and_lifecycle(self):
        manager = SubagentManager(allow_subagents=True, max_subagents_per_job=2, max_depth=1)

        # 1. Create first subagent
        sub1 = manager.create_subagent(parent_agent_id="claude", task="Inspect race condition", capabilities=["review.code"])
        self.assertIsNotNone(sub1)
        self.assertEqual(sub1.parentAgentId, "claude")
        self.assertEqual(sub1.depth, 1)
        self.assertIn("review.code", sub1.capabilities)

        # 2. Create second subagent
        sub2 = manager.create_subagent(parent_agent_id="claude", task="Inspect deadlock", capabilities=["review.concurrency"])
        self.assertIsNotNone(sub2)

        # 3. Third subagent exceeds max_subagents_per_job=2 -> rejected
        sub3 = manager.create_subagent(parent_agent_id="claude", task="Third task")
        self.assertIsNone(sub3)

        # 4. Nested depth > 1 -> rejected
        sub_nested = manager.create_subagent(parent_agent_id=sub1.id, task="Nested subtask", parent_depth=1)
        self.assertIsNone(sub_nested)

    def test_subagents_disabled_by_default(self):
        manager = SubagentManager(allow_subagents=False)
        sub = manager.create_subagent(parent_agent_id="claude", task="Task when disabled")
        self.assertIsNone(sub)



class TestPhase7SecurityAndLimits(unittest.TestCase):
    def test_forged_privilege_keys_in_delegation_output_are_ignored(self):
        raw_stdout = f"""
{LYSSTACK_DELEGATION_START}
{{
  "task": "Perform audit",
  "requiredCapabilities": ["review.code"],
  "permissions": ["sudo", "shell:all"],
  "tools": ["arbitrary_exec"]
}}
{LYSSTACK_DELEGATION_END}
"""
        turn_result = parse_a2a_output(raw_stdout)
        self.assertEqual(len(turn_result.delegation_requests), 1)
        del_req = turn_result.delegation_requests[0]
        self.assertEqual(del_req.task, "Perform audit")
        # Ensure forged permissions are not permitted as attributes
        self.assertFalse(hasattr(del_req, "sudo"))
        self.assertFalse(hasattr(del_req, "arbitrary_exec"))

    def test_delegation_limit_reached_halts_and_emits_event(self):
        mod = _get_runner_module()
        HermesSprintRunner = mod.HermesSprintRunner

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            p1 = tmp_root / "p1.md"
            p1.write_text("Prompt 1", encoding="utf-8")

            spec_path = ROOT_DIR / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=False)
            runner.job_id = "job_limit_test"
            runner.thread_id = "thread_job_limit_test"
            runner.run_dir = tmp_root / "runs" / "test_limit"
            runner.run_dir.mkdir(parents=True, exist_ok=True)
            runner.messages_file = runner.run_dir / "messages.jsonl"
            runner.worktree_root = tmp_root / "worktrees"
            (runner.worktree_root / "worker").mkdir(parents=True, exist_ok=True)
            runner.limits["delegation"] = {"max_delegations_per_job": 1}

            phase = {"name": "01_builder", "role": "builder", "agent": "gemini", "worktree_dir": "worker", "prompt_file": str(p1)}
            runner.spec["phases"] = [phase]

            runner.job_delegations = 1  # Already at limit 1

            turn_result = AgentTurnResult(
                execution_result=None,
                text="Output",
                delegation_requests=[
                    DelegationRequest(task="Task beyond limit", requiredCapabilities=["review.code"])
                ],
            )

            # In schedule_a2a_turns, this should skip delegation
            mock_pub = MagicMock()
            mock_pub.enabled = True
            orig_pub = mod.default_publisher
            mod.default_publisher = mock_pub

            try:
                # Stub execute_agent to return turn_result
                runner.execute_agent = lambda *args, **kwargs: turn_result
                runner._record_message(
                    from_actor={"id": "operator", "kind": "user", "displayName": "Operator"},
                    to_actors=[{"id": "gemini", "kind": "agent", "displayName": "Gemini"}],
                    kind="operator",
                    intent="question",
                    text="Go",
                    conversation_id="conv_lim",
                )
                runner.schedule_a2a_turns(phase, runner.worktree_root / "worker", conversation_id="conv_lim")

                # Verify delegation.limit_reached was published
                mock_pub.publish.assert_any_call(
                    source_id="hermes_runner",
                    source_kind="runtime",
                    kind="delegation.limit_reached",
                    detail="Delegation limit reached (1/1).",
                    job_id="job_limit_test",
                    metadata={"delegationId": turn_result.delegation_requests[0].id, "count": 1},
                )
            finally:
                mod.default_publisher = orig_pub


class TestPhase7SubagentExecutionIntegration(unittest.TestCase):
    def test_subagent_spawned_and_scheduled_when_no_registered_actor_matches(self):
        mod = _get_runner_module()
        HermesSprintRunner = mod.HermesSprintRunner

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            p1 = tmp_root / "p1.md"
            p1.write_text("Prompt 1", encoding="utf-8")

            spec_path = ROOT_DIR / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=False)
            runner.job_id = "job_sub_e2e"
            runner.thread_id = "thread_job_sub_e2e"
            runner.run_dir = tmp_root / "runs" / "test_sub"
            runner.run_dir.mkdir(parents=True, exist_ok=True)
            runner.messages_file = runner.run_dir / "messages.jsonl"
            runner.worktree_root = tmp_root / "worktrees"
            (runner.worktree_root / "worker").mkdir(parents=True, exist_ok=True)

            # Enable subagents
            runner.limits["delegation"] = {"allow_subagents": True, "max_subagents_per_job": 2, "max_depth": 1}
            runner.subagent_manager.allow_subagents = True

            phase = {"name": "02_hardener", "role": "hardener", "agent": "claude", "worktree_dir": "worker", "prompt_file": str(p1)}
            runner.spec["phases"] = [phase]

            conv_id = "conv_subagent_flow"
            runner._record_message(
                from_actor={"id": "operator", "kind": "user", "displayName": "Operator"},
                to_actors=[{"id": "claude", "kind": "agent", "displayName": "Claude"}],
                kind="operator",
                intent="question",
                text="Please delegate to ephemeral subagent.",
                conversation_id=conv_id,
            )

            executed_actors = []

            def stub_execute(context):
                actor_id = context.phase["agent"]
                executed_actors.append(actor_id)

                # Claude requests subagent delegation for rare capability
                if actor_id == "claude" and len(executed_actors) == 1:
                    raw_stdout = f"""
Claude requesting subagent:
{LYSSTACK_DELEGATION_START}
{{
  "task": "Deep static analysis on memory layout",
  "requiredCapabilities": ["specialized.memory_inspection"],
  "allowSubagent": true
}}
{LYSSTACK_DELEGATION_END}
"""
                # Subagent executes and finishes
                elif "subagent" in actor_id:
                    raw_stdout = f"""
Subagent completed memory inspection.
{LYSSTACK_A2A_START}
{{
  "intent": "task_result",
  "to": ["claude"],
  "text": "Memory layout verified safe.",
  "conversationId": "{conv_id}"
}}
{LYSSTACK_A2A_END}
"""
                else:
                    raw_stdout = "Done."

                return ExecutionResult(command=[actor_id], returncode=0, stdout=raw_stdout, stderr="", backend="subprocess")

            mock_registry = MagicMock()
            mock_adapter = MagicMock()
            mock_adapter.execute.side_effect = stub_execute
            mock_registry.get.return_value = mock_adapter
            runner.agent_registry = mock_registry

            runner.schedule_a2a_turns(phase, runner.worktree_root / "worker", conversation_id=conv_id)

            # Assert execution: Claude -> subagent_claude_1
            self.assertEqual(len(executed_actors), 2)
            self.assertEqual(executed_actors[0], "claude")
            self.assertTrue(executed_actors[1].startswith("subagent_claude_"))

            # Verify subagent profile in manager
            self.assertEqual(len(runner.subagent_manager.list_subagents()), 1)
            sub_profile = runner.subagent_manager.list_subagents()[0]
            self.assertEqual(sub_profile.parentAgentId, "claude")
            self.assertEqual(sub_profile.depth, 1)


if __name__ == "__main__":
    unittest.main()
