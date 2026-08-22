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
    ToolPolicy,
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
            runner.spec["limits"]["allowed_tools"] = ["tool.git.inspect"]
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

            claude_invocations = []
            # Claude emits tool request on turn 1, then handles tool result on turn 2
            def stub_claude_execute(context):
                claude_invocations.append(context)
                if len(claude_invocations) == 1:
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
                else:
                    # Continuation turn: receives tool result in context and concludes
                    raw_stdout = f"""
Claude received tool output.
{LYSSTACK_A2A_START}
{{
  "intent": "review_result",
  "to": ["operator"],
  "text": "Code review complete: git diff inspected.",
  "conversationId": "{conv_id}"
}}
{LYSSTACK_A2A_END}
"""
                return ExecutionResult(command=["claude"], returncode=0, stdout=raw_stdout, stderr="", backend="subprocess")

            mock_registry = MagicMock()
            mock_adapter = MagicMock()
            mock_adapter.execute.side_effect = stub_claude_execute
            mock_registry.get.return_value = mock_adapter
            runner.agent_registry = mock_registry

            runner.schedule_a2a_turns(phase, target_repo, conversation_id=conv_id)

            # Assert 2 turns executed (Turn 1 tool request, Turn 2 tool result continuation)
            self.assertEqual(len(claude_invocations), 2)

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
            requester={"id": "claude", "kind": "agent"},
        )
        res = default_tool_registry.execute(treq, job_config={"limits": {"allowed_tools": ["tool.git.inspect"]}})
        self.assertEqual(res.status, "rejected")
        self.assertIn("not permitted", res.error)

    def test_unregistered_tool_rejected(self):
        treq = ToolInvocationRequest(
            toolId="tool.arbitrary.malicious",
            args={"cmd": "rm -rf /"},
            requester={"id": "claude", "kind": "agent"},
        )
        res = default_tool_registry.execute(treq, job_config={"limits": {"allowed_tools": ["tool.arbitrary.malicious"]}})
        self.assertEqual(res.status, "rejected")
        self.assertIn("not registered", res.error)


class TestPhase7SubagentsBoundedManagement(unittest.TestCase):
    """
    ABSOLUTE ACCEPTANCE TEST C:
    Subagent creation is bounded, controller-owned, and uses the standard ActorRef/Message transport.
    """

    def test_subagent_manager_limits_and_lifecycle(self):
        manager = SubagentManager(allow_subagents=True, max_subagents_per_job=2, max_depth=1, allowed_capabilities=["review.code", "review.concurrency", "general-execution"])

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

            # Enable subagents with explicit allowed_capabilities
            runner.limits["delegation"] = {"allow_subagents": True, "max_subagents_per_job": 2, "max_depth": 1, "allowed_capabilities": ["specialized.memory_inspection"]}
            runner.subagent_manager.allow_subagents = True
            runner.subagent_manager.allowed_capabilities = {"specialized.memory_inspection"}

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



class TestPhase7_1_RuntimePolicyPatches(unittest.TestCase):
    """
    Focused regression test suite for Phase 7.1 runtime policy patches:
    1. bind subagent identity -> parent/provider adapter
    2. controller-allowlist subagent capabilities
    3. propagate true parent depth
    4. enforce actor capability + allowed_tools + tool policy
    5. add real tool-result continuation
    6. regression tests for all paths
    """

    def test_bind_subagent_identity_to_parent_provider_adapter(self):
        mod = _get_runner_module()
        HermesSprintRunner = mod.HermesSprintRunner
        from runner.agents.antigravity import AntigravityAdapter
        from runner.agents.claude import ClaudeAdapter
        from runner.agents.codex import CodexAdapter
        from runner.agents.registry import default_registry

        # 1. AgentRegistry resolves subagent IDs to parent/provider adapters
        self.assertIsInstance(default_registry.get("subagent_gemini_1"), AntigravityAdapter)
        self.assertIsInstance(default_registry.get("subagent_claude_1"), ClaudeAdapter)
        self.assertIsInstance(default_registry.get("subagent_codex_1"), CodexAdapter)
        self.assertIsInstance(default_registry.get("subagent_custom_1", parent_provider="claude"), ClaudeAdapter)

        # 2. SubagentProfile stores provider
        manager = SubagentManager(allow_subagents=True, max_subagents_per_job=3, max_depth=2, allowed_capabilities=["general-execution"])
        sub1 = manager.create_subagent(parent_agent_id="claude", task="Subtask 1")
        self.assertEqual(sub1.provider, "claude")

        sub2 = manager.create_subagent(parent_agent_id="gemini", task="Subtask 2")
        self.assertEqual(sub2.provider, "antigravity")

        # 3. Runner execute_agent resolves subagent provider adapter seamlessly
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            p1 = tmp_root / "p1.md"
            p1.write_text("Prompt content", encoding="utf-8")

            spec_path = ROOT_DIR / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=True)
            runner.subagent_manager = manager

            phase = {
                "name": "subagent_claude_1",
                "role": "hardener",
                "agent": sub1.id,
                "worktree_dir": "worker",
                "prompt_file": str(p1),
            }

            # execute_agent should find Claude adapter via subagent manager profile without raising FAILED_UNKNOWN_AGENT
            mock_adapter = MagicMock()
            mock_adapter.execute.return_value = ExecutionResult(command=["subagent"], returncode=0, stdout="OK", stderr="", backend="subprocess")
            runner.agent_registry = MagicMock()
            runner.agent_registry.get.return_value = mock_adapter

            wt = tmp_root / "worker"
            wt.mkdir(parents=True, exist_ok=True)
            res = runner.execute_agent(phase, wt)
            self.assertEqual(res.returncode, 0)
            runner.agent_registry.get.assert_called_with("subagent_claude_1")

    def test_controller_allowlist_subagent_capabilities(self):
        mock_pub = MagicMock()
        manager = SubagentManager(
            allow_subagents=True,
            max_subagents_per_job=5,
            max_depth=2,
            allowed_capabilities=["code.python", "testing.unit", "review.code"],
        )

        # 1. Permitted capability request succeeds
        sub_allowed = manager.create_subagent(
            parent_agent_id="claude",
            task="Valid task",
            capabilities=["code.python", "testing.unit"],
            publisher=mock_pub,
            job_id="job_allowlist_test",
        )
        self.assertIsNotNone(sub_allowed)
        self.assertEqual(sub_allowed.capabilities, ["code.python", "testing.unit"])

        # 2. Unallowlisted capability request is REJECTED by controller policy
        sub_disallowed = manager.create_subagent(
            parent_agent_id="claude",
            task="Dangerous task",
            capabilities=["code.python", "dangerous.escalation.cap"],
            publisher=mock_pub,
            job_id="job_allowlist_test",
        )
        self.assertIsNone(sub_disallowed)
        mock_pub.publish.assert_any_call(
            source_id="subagent_manager",
            source_kind="runtime",
            kind="delegation.rejected",
            detail="Subagent capabilities ['dangerous.escalation.cap'] not permitted by controller allowlist (allowed: ['code.python', 'review.code', 'testing.unit']).",
            job_id="job_allowlist_test",
            metadata={
                "reason": "capabilities_not_allowlisted",
                "disallowedCapabilities": ["dangerous.escalation.cap"],
                "allowedCapabilities": ["code.python", "review.code", "testing.unit"],
            },
        )

    def test_propagate_true_parent_depth(self):
        mock_pub = MagicMock()
        manager = SubagentManager(
            allow_subagents=True,
            max_subagents_per_job=5,
            max_depth=2,
            allowed_capabilities=["general-execution"],
        )

        # 1. Root agent (parent_depth=0) creates depth 1 subagent
        sub1 = manager.create_subagent(
            parent_agent_id="claude",
            task="Depth 1 task",
            parent_depth=0,
            publisher=mock_pub,
            job_id="job_depth_test",
        )
        self.assertIsNotNone(sub1)
        self.assertEqual(sub1.depth, 1)

        # 2. Depth 1 subagent creates depth 2 subagent (parent_depth=1)
        sub2 = manager.create_subagent(
            parent_agent_id=sub1.id,
            task="Depth 2 task",
            parent_depth=sub1.depth,
            publisher=mock_pub,
            job_id="job_depth_test",
        )
        self.assertIsNotNone(sub2)
        self.assertEqual(sub2.depth, 2)
        self.assertEqual(sub2.parentAgentId, sub1.id)

        # 3. Depth 2 subagent attempting to create depth 3 subagent exceeds max_depth=2 -> REJECTED
        sub3 = manager.create_subagent(
            parent_agent_id=sub2.id,
            task="Depth 3 task",
            parent_depth=sub2.depth,
            publisher=mock_pub,
            job_id="job_depth_test",
        )
        self.assertIsNone(sub3)
        mock_pub.publish.assert_any_call(
            source_id="subagent_manager",
            source_kind="runtime",
            kind="delegation.limit_reached",
            detail="Subagent depth (3) exceeds maximum permitted depth (2).",
            job_id="job_depth_test",
            metadata={"reason": "max_depth_exceeded", "requestedDepth": 3, "maxDepth": 2},
        )

    def test_enforce_actor_capability_on_tool_invocation(self):
        cap_reg = create_default_capability_registry()

        # Actor 'gemini' does NOT have 'git.inspect' or 'repo.read'
        treq_gemini = ToolInvocationRequest(
            toolId="tool.git.inspect",
            args={"operation": "status"},
            requester={"id": "gemini", "kind": "agent"},
        )
        res_gemini = default_tool_registry.execute(
            request=treq_gemini,
            job_config={"limits": {"allowed_tools": ["tool.git.inspect"]}},
            capability_registry=cap_reg,
        )
        self.assertEqual(res_gemini.status, "rejected")
        self.assertIn("lacks required capabilities", res_gemini.error)
        self.assertIn("tool.git.inspect", res_gemini.error)

        # Actor 'claude' has 'git.inspect' -> capability check passes
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_repo = Path(tmp_dir)
            subprocess.run(["git", "init", "-b", "main"], cwd=tmp_repo, check=True, capture_output=True)
            treq_claude = ToolInvocationRequest(
                toolId="tool.git.inspect",
                args={"operation": "status"},
                requester={"id": "claude", "kind": "agent"},
            )
            res_claude = default_tool_registry.execute(
                request=treq_claude,
                worktree_dir=tmp_repo,
                job_config={"limits": {"allowed_tools": ["tool.git.inspect"]}},
                capability_registry=cap_reg,
            )
            self.assertEqual(res_claude.status, "success")

        # Actor 'gemini' HAS 'testing.unit' -> can invoke tool.test_runner
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_wt = Path(tmp_dir)
            treq_test = ToolInvocationRequest(
                toolId="tool.test_runner",
                args={"target": "nonexistent_test.py"},
                requester={"id": "gemini", "kind": "agent"},
            )
            res_test = default_tool_registry.execute(
                request=treq_test,
                worktree_dir=tmp_wt,
                job_config={"limits": {"allowed_tools": ["tool.test_runner"], "allow_test_runner_fallback": True}},
                capability_registry=cap_reg,
            )
            # Capability check passed (failed only because test file does not exist, not rejected)
            self.assertIn(res_test.status, ["success", "failed"])
            self.assertNotEqual(res_test.status, "rejected")

    def test_enforce_allowed_tools_and_tool_policy(self):
        cap_reg = create_default_capability_registry()

        # 1. Job limits allow_tools = False -> REJECTED
        job_config_disabled = {"limits": {"allow_tools": False}}
        treq = ToolInvocationRequest(
            toolId="tool.git.inspect",
            args={"operation": "status"},
            requester={"id": "claude", "kind": "agent"},
        )
        res_disabled = default_tool_registry.execute(
            request=treq,
            job_config=job_config_disabled,
            capability_registry=cap_reg,
        )
        self.assertEqual(res_disabled.status, "rejected")
        self.assertIn("disabled by job policy", res_disabled.error)

        # 2. Job limits allowed_tools restriction -> tool not in list is REJECTED
        job_config_restricted = {"limits": {"allowed_tools": ["tool.test_runner"]}}
        res_restricted = default_tool_registry.execute(
            request=treq,
            job_config=job_config_restricted,
            capability_registry=cap_reg,
        )
        self.assertEqual(res_restricted.status, "rejected")
        self.assertIn("not permitted for this job", res_restricted.error)

        # 3. Disallowed flag option in git inspect -> REJECTED
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_repo = Path(tmp_dir)
            treq_flag = ToolInvocationRequest(
                toolId="tool.git.inspect",
                args={"operation": "diff", "target": "--exec=malicious"},
                requester={"id": "claude", "kind": "agent"},
            )
            res_flag = default_tool_registry.execute(
                request=treq_flag,
                worktree_dir=tmp_repo,
                job_config={"limits": {"allowed_tools": ["tool.git.inspect"]}},
                capability_registry=cap_reg,
            )
            self.assertEqual(res_flag.status, "rejected")
            self.assertIn("Disallowed flag option", res_flag.error)

    def test_real_tool_result_continuation(self):
        """
        Tests the full two-turn tool continuation loop:
        Turn 1: Claude requests tool.git.inspect.
        Hermes executes tool, generates tool_result message.
        Turn 2: Claude receives tool_result continuation turn, processes output, and emits terminal review_result.
        """
        mod = _get_runner_module()
        HermesSprintRunner = mod.HermesSprintRunner

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            target_repo = tmp_root / "repo"
            target_repo.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=target_repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=target_repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=target_repo, check=True)
            (target_repo / "service.py").write_text("# initial service\n", encoding="utf-8")
            subprocess.run(["git", "add", "service.py"], cwd=target_repo, check=True)
            subprocess.run(["git", "commit", "-m", "initial commit"], cwd=target_repo, check=True)
            (target_repo / "service.py").write_text("# updated service with mutex guard\n", encoding="utf-8")

            p1 = tmp_root / "p1.md"
            p1.write_text("Hardener prompt", encoding="utf-8")

            spec_path = ROOT_DIR / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=False)
            runner.job_id = "job_continuation_e2e"
            runner.thread_id = "thread_job_continuation_e2e"
            runner.run_dir = tmp_root / "runs" / "test_continuation"
            runner.run_dir.mkdir(parents=True, exist_ok=True)
            runner.messages_file = runner.run_dir / "messages.jsonl"
            runner.worktree_root = target_repo.parent

            phase = {
                "name": "02_hardener",
                "role": "hardener",
                "agent": "claude",
                "worktree_dir": target_repo.name,
                "prompt_file": str(p1),
            }
            runner.spec["phases"] = [phase]
            runner.spec["limits"]["allowed_tools"] = ["tool.git.inspect"]

            conv_id = "conv_tool_continuation_e2e"
            runner._record_message(
                from_actor={"id": "operator", "kind": "user", "displayName": "Operator"},
                to_actors=[{"id": "claude", "kind": "agent", "displayName": "Claude"}],
                kind="operator",
                intent="question",
                text="Please inspect the service diff.",
                conversation_id=conv_id,
            )

            turns_executed = []

            def stub_claude_execute(context):
                turns_executed.append(context)
                turn_num = len(turns_executed)

                if turn_num == 1:
                    # Turn 1: request tool execution
                    raw_stdout = f"""
Claude analyzing code:
Requesting git diff via controlled tool.
{LYSSTACK_TOOL_REQUEST_START}
{{
  "toolId": "tool.git.inspect",
  "args": {{
    "operation": "diff"
  }}
}}
{LYSSTACK_TOOL_REQUEST_END}
"""
                elif turn_num == 2:
                    # Turn 2: continuation turn with tool result in context
                    raw_stdout = f"""
Claude received tool inspection result:
Verified diff contains mutex guard.
{LYSSTACK_A2A_START}
{{
  "intent": "review_result",
  "to": ["operator"],
  "text": "Review complete: mutex guard confirmed present and correct.",
  "conversationId": "{conv_id}"
}}
{LYSSTACK_A2A_END}
"""
                else:
                    raw_stdout = "No further action."

                return ExecutionResult(command=["claude"], returncode=0, stdout=raw_stdout, stderr="", backend="subprocess")

            mock_registry = MagicMock()
            mock_adapter = MagicMock()
            mock_adapter.execute.side_effect = stub_claude_execute
            mock_registry.get.return_value = mock_adapter
            runner.agent_registry = mock_registry

            # Run scheduler loop
            runner.schedule_a2a_turns(phase, target_repo, conversation_id=conv_id)

            # Assert exactly 2 turns were executed
            self.assertEqual(len(turns_executed), 2)
            self.assertEqual(runner.job_a2a_turns, 2)

            # Verify message flow sequence:
            # 1. operator question
            # 2. tool_result from tool.git.inspect to claude
            # 3. review_result from claude to operator
            tool_msg = next((m for m in runner.local_messages if m.get("kind") == "tool_result"), None)
            self.assertIsNotNone(tool_msg)
            self.assertEqual(tool_msg["from"]["id"], "tool.git.inspect")
            self.assertEqual(tool_msg["to"][0]["id"], "claude")
            self.assertIn("mutex guard", tool_msg["text"])

            review_msg = next((m for m in runner.local_messages if m.get("intent") == "review_result"), None)
            self.assertIsNotNone(review_msg)
            self.assertEqual(review_msg["from"]["id"], "claude")
            self.assertEqual(review_msg["to"][0]["id"], "operator")
            self.assertIn("mutex guard confirmed present", review_msg["text"])


class TestPhase7_2_PolicyHardeningFailClosed(unittest.TestCase):
    """
    Phase 7.2 fail-closed policy hardening regression tests:
    1. If subagents enabled: require controller allowed_capabilities.
    2. If tools enabled: require explicit allowed_tools.
    3. Actually enforce ToolPolicy: max timeout & read-only constraint.
    4. tool.test_runner: configured commands only, unless safe fallback explicitly enabled.
    5. Missing-policy fail-closed behavior tests.
    """

    def test_subagents_enabled_without_allowed_capabilities_fails_closed(self):
        mock_pub = MagicMock()

        # 1. allow_subagents=True but allowed_capabilities is None -> REJECTED
        manager_none = SubagentManager(allow_subagents=True, allowed_capabilities=None)
        sub_none = manager_none.create_subagent(
            parent_agent_id="claude",
            task="Task without allowed_capabilities config",
            publisher=mock_pub,
            job_id="job_fc_1",
        )
        self.assertIsNone(sub_none)
        mock_pub.publish.assert_any_call(
            source_id="subagent_manager",
            source_kind="runtime",
            kind="delegation.rejected",
            detail="Subagent creation rejected: controller allowed_capabilities must be explicitly configured when subagents are enabled.",
            job_id="job_fc_1",
            metadata={"reason": "missing_allowed_capabilities_policy", "parentAgentId": "claude"},
        )

        # 2. allow_subagents=True but allowed_capabilities is empty list -> REJECTED
        manager_empty = SubagentManager(allow_subagents=True, allowed_capabilities=[])
        sub_empty = manager_empty.create_subagent(
            parent_agent_id="claude",
            task="Task with empty allowed_capabilities config",
            publisher=mock_pub,
            job_id="job_fc_2",
        )
        self.assertIsNone(sub_empty)

        # 3. Explicit allowed_capabilities -> ALLOWED
        manager_valid = SubagentManager(allow_subagents=True, allowed_capabilities=["review.code"])
        sub_valid = manager_valid.create_subagent(
            parent_agent_id="claude",
            task="Valid task",
            capabilities=["review.code"],
        )
        self.assertIsNotNone(sub_valid)

    def test_tools_enabled_without_explicit_allowed_tools_fails_closed(self):
        mock_pub = MagicMock()
        treq = ToolInvocationRequest(
            toolId="tool.git.inspect",
            args={"operation": "status"},
            requester={"id": "claude", "kind": "agent"},
        )

        # 1. No job_config (missing allowed_tools) -> REJECTED
        res_no_config = default_tool_registry.execute(request=treq, publisher=mock_pub, job_id="job_tc_1")
        self.assertEqual(res_no_config.status, "rejected")
        self.assertIn("allowed_tools must be explicitly configured", res_no_config.error)
        mock_pub.publish.assert_any_call(
            source_id="hermes_runner",
            source_kind="runtime",
            kind="tool.rejected",
            detail="Tool execution rejected: allowed_tools must be explicitly configured by controller policy.",
            job_id="job_tc_1",
            metadata={"requestId": treq.id, "toolId": "tool.git.inspect", "reason": "missing_allowed_tools_policy"},
        )

        # 2. job_config with empty limits (missing allowed_tools) -> REJECTED
        res_empty_limits = default_tool_registry.execute(request=treq, job_config={"limits": {}})
        self.assertEqual(res_empty_limits.status, "rejected")
        self.assertIn("allowed_tools must be explicitly configured", res_empty_limits.error)

        # 3. Explicit allowed_tools provided -> ALLOWED
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_repo = Path(tmp_dir)
            subprocess.run(["git", "init", "-b", "main"], cwd=tmp_repo, check=True, capture_output=True)
            res_valid = default_tool_registry.execute(
                request=treq,
                worktree_dir=tmp_repo,
                job_config={"limits": {"allowed_tools": ["tool.git.inspect"]}},
            )
            self.assertEqual(res_valid.status, "success")

    def test_tool_policy_enforces_max_timeout_and_read_only_constraints(self):
        cap_reg = create_default_capability_registry()

        # 1. Max timeout clamped by ToolPolicy
        treq_long = ToolInvocationRequest(
            toolId="tool.git.inspect",
            args={"operation": "status"},
            timeoutSeconds=9999,
            requester={"id": "claude", "kind": "agent"},
        )
        policy = ToolPolicy(allowed_tools=["tool.git.inspect"], max_timeout_seconds=25)
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_repo = Path(tmp_dir)
            subprocess.run(["git", "init", "-b", "main"], cwd=tmp_repo, check=True, capture_output=True)
            res = default_tool_registry.execute(
                request=treq_long,
                worktree_dir=tmp_repo,
                job_config={"limits": {"tool_policy": policy}},
                capability_registry=cap_reg,
            )
            self.assertEqual(res.status, "success")
            self.assertEqual(treq_long.timeoutSeconds, 25)

        # 2. Non-read-only tool rejected when read_only_only is True
        mutating_profile = ToolProfile(
            id="tool.custom.mutating",
            displayName="Mutating Tool",
            capabilities=["testing.unit"],
            metadata={"readOnly": False},
        )
        default_tool_registry.register_tool(mutating_profile, lambda req, wt, jc: ToolInvocationResult(requestId=req.id, toolId=req.toolId, status="success"))

        treq_mut = ToolInvocationRequest(
            toolId="tool.custom.mutating",
            args={},
            requester={"id": "gemini", "kind": "agent"},
        )
        res_mut = default_tool_registry.execute(
            request=treq_mut,
            job_config={"limits": {"allowed_tools": ["tool.custom.mutating"], "read_only_tools_only": True}},
            capability_registry=cap_reg,
        )
        self.assertEqual(res_mut.status, "rejected")
        self.assertIn("violates read_only_only tool policy", res_mut.error)

    def test_tool_test_runner_rejects_unconfigured_command_when_fallback_disabled(self):
        cap_reg = create_default_capability_registry()
        treq = ToolInvocationRequest(
            toolId="tool.test_runner",
            args={"target": "tests/test_foo.py"},
            requester={"id": "gemini", "kind": "agent"},
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_wt = Path(tmp_dir)

            # 1. No verification commands and fallback NOT enabled -> REJECTED
            res_rejected = default_tool_registry.execute(
                request=treq,
                worktree_dir=tmp_wt,
                job_config={"limits": {"allowed_tools": ["tool.test_runner"]}},
                capability_registry=cap_reg,
            )
            self.assertEqual(res_rejected.status, "rejected")
            self.assertIn("no verification command configured", res_rejected.error)

            # 2. Fallback explicitly enabled -> safe fallback executed
            res_fallback = default_tool_registry.execute(
                request=treq,
                worktree_dir=tmp_wt,
                job_config={"limits": {"allowed_tools": ["tool.test_runner"], "allow_test_runner_fallback": True}},
                capability_registry=cap_reg,
            )
            self.assertIn(res_fallback.status, ["success", "failed"])
            self.assertNotEqual(res_fallback.status, "rejected")

            # 3. Configured verification command in job_config -> executed configured command
            res_configured = default_tool_registry.execute(
                request=treq,
                worktree_dir=tmp_wt,
                job_config={
                    "limits": {"allowed_tools": ["tool.test_runner"]},
                    "verification": [{"name": "tests", "command": ["echo", "verification_ok"]}],
                },
                capability_registry=cap_reg,
            )
            self.assertEqual(res_configured.status, "success")
            self.assertIn("verification_ok", res_configured.output.get("stdout", ""))


if __name__ == "__main__":
    unittest.main()
