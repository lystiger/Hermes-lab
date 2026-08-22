import importlib.util
import json
import os
import sys
import tempfile
import unittest
import urllib.request
import urllib.parse
import threading
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

from a2a import (
    A2AOutput,
    AgentTurnResult,
    A2AOutputParser,
    parse_a2a_output,
    validate_reply_to,
    SCHEDULABLE_INTENTS,
    TERMINAL_INTENTS,
    LYSSTACK_A2A_START,
    LYSSTACK_A2A_END,
)
from persona import resolve_agent_profile, PersonaProfile, AgentProfile
from persona_loader import PersonaLoader
from message_router import MessageRouter
from message_store import MessageStore
from event_bus import RuntimeEventBus
from runner.backends.base import ExecutionResult


class TestPhase61A2AOutputParser(unittest.TestCase):
    def setUp(self):
        self.bus = RuntimeEventBus()
        self.publisher = MagicMock()

    def test_parse_valid_single_a2a_output_block(self):
        raw_stdout = """
Initial thoughts on the implementation:
The mutex placement in state.py needs adjustment.

--- LYSSTACK A2A OUTPUT ---
{
  "intent": "correction_request",
  "to": ["gemini"],
  "text": "The scheduler reset path still races with queue mutation.",
  "conversationId": "conv_scheduler_review",
  "replyTo": "msg_gemini_001",
  "correlationId": "corr_review_01"
}
--- END LYSSTACK A2A OUTPUT ---

End of execution report.
"""
        exec_res = ExecutionResult(
            command=["claude", "run"],
            returncode=0,
            stdout=raw_stdout,
            stderr="",
            backend="subprocess",
        )
        turn_result = parse_a2a_output(raw_stdout, execution_result=exec_res)

        self.assertIsInstance(turn_result, AgentTurnResult)
        self.assertEqual(len(turn_result.outgoing_messages), 1)
        out = turn_result.outgoing_messages[0]
        self.assertEqual(out.intent, "correction_request")
        self.assertEqual(out.to, ["gemini"])
        self.assertEqual(out.text, "The scheduler reset path still races with queue mutation.")
        self.assertEqual(out.conversationId, "conv_scheduler_review")
        self.assertEqual(out.replyTo, "msg_gemini_001")
        self.assertEqual(out.correlationId, "corr_review_01")
        self.assertEqual(turn_result.returncode, 0)
        self.assertEqual(turn_result.backend, "subprocess")

    def test_parse_no_a2a_block_tolerated(self):
        raw_stdout = "Standard terminal output without structured A2A block. Code looks great!"
        turn_result = parse_a2a_output(raw_stdout)
        self.assertIsInstance(turn_result, AgentTurnResult)
        self.assertEqual(len(turn_result.outgoing_messages), 0)
        self.assertEqual(turn_result.stdout, raw_stdout)

    def test_parse_malformed_json_emits_diagnostic_and_does_not_crash(self):
        raw_stdout = """
--- LYSSTACK A2A OUTPUT ---
{
  "intent": "correction_request",
  "to": ["gemini",
  "text": broken json syntax...
}
--- END LYSSTACK A2A OUTPUT ---
"""
        turn_result = parse_a2a_output(raw_stdout, publisher=self.publisher, job_id="job_malformed", agent_id="claude")
        self.assertIsInstance(turn_result, AgentTurnResult)
        self.assertEqual(len(turn_result.outgoing_messages), 0)
        self.publisher.publish.assert_called_once()
        call_kwargs = self.publisher.publish.call_args[1]
        self.assertEqual(call_kwargs["kind"], "conversation.invalid_a2a_output")
        self.assertEqual(call_kwargs["source_id"], "claude")

    def test_parse_empty_to_recipient_list_ignored(self):
        raw_stdout = """
--- LYSSTACK A2A OUTPUT ---
{
  "intent": "question",
  "to": [],
  "text": "Who should answer this?"
}
--- END LYSSTACK A2A OUTPUT ---
"""
        turn_result = parse_a2a_output(raw_stdout, publisher=self.publisher)
        self.assertEqual(len(turn_result.outgoing_messages), 0)
        self.publisher.publish.assert_called_once()
        self.assertEqual(self.publisher.publish.call_args[1]["kind"], "conversation.invalid_a2a_output")

    def test_forbidden_privilege_keys_stripped_from_a2a_output(self):
        raw_stdout = """
--- LYSSTACK A2A OUTPUT ---
{
  "intent": "correction_request",
  "to": ["gemini"],
  "text": "Please fix permissions.",
  "metadata": {
    "module": "auth",
    "permissions": ["sudo", "root"],
    "tools": ["rm -rf"],
    "shell": "/bin/bash",
    "safe_key": "safe_value"
  }
}
--- END LYSSTACK A2A OUTPUT ---
"""
        turn_result = parse_a2a_output(raw_stdout)
        self.assertEqual(len(turn_result.outgoing_messages), 1)
        meta = turn_result.outgoing_messages[0].metadata
        self.assertIn("module", meta)
        self.assertIn("safe_key", meta)
        self.assertNotIn("permissions", meta)
        self.assertNotIn("tools", meta)
        self.assertNotIn("shell", meta)


class TestPhase61ReplyToValidation(unittest.TestCase):
    def setUp(self):
        self.publisher = MagicMock()
        self.known_messages = [
            {
                "id": "msg_001",
                "threadId": "thread_alpha",
                "jobId": "job_101",
                "conversationId": "conv_review",
                "text": "Initial review request",
            },
            {
                "id": "msg_002",
                "threadId": "thread_alpha",
                "jobId": "job_101",
                "conversationId": "conv_review",
                "text": "First correction",
            },
            {
                "id": "msg_other_thread",
                "threadId": "thread_beta",
                "jobId": "job_101",
                "conversationId": "conv_review",
                "text": "Message from another thread",
            },
            {
                "id": "msg_other_job",
                "threadId": "thread_alpha",
                "jobId": "job_999_other",
                "conversationId": "conv_review",
                "text": "Message from another job",
            },
            {
                "id": "msg_other_conv",
                "threadId": "thread_alpha",
                "jobId": "job_101",
                "conversationId": "conv_other",
                "text": "Message from another conversation",
            },
        ]

    def test_valid_same_conversation_reply_to_passes(self):
        is_valid = validate_reply_to(
            reply_to="msg_001",
            thread_id="thread_alpha",
            conversation_id="conv_review",
            known_messages=self.known_messages,
            job_id="job_101",
            publisher=self.publisher,
        )
        self.assertTrue(is_valid)
        self.publisher.publish.assert_not_called()

    def test_nonexistent_reply_to_rejected(self):
        is_valid = validate_reply_to(
            reply_to="msg_nonexistent_999",
            thread_id="thread_alpha",
            conversation_id="conv_review",
            known_messages=self.known_messages,
            job_id="job_101",
            publisher=self.publisher,
        )
        self.assertFalse(is_valid)
        self.publisher.publish.assert_called_once()
        self.assertEqual(self.publisher.publish.call_args[1]["kind"], "conversation.invalid_reply")

    def test_cross_thread_reply_to_rejected(self):
        is_valid = validate_reply_to(
            reply_to="msg_other_thread",
            thread_id="thread_alpha",
            conversation_id="conv_review",
            known_messages=self.known_messages,
            job_id="job_101",
            publisher=self.publisher,
        )
        self.assertFalse(is_valid)
        self.publisher.publish.assert_called_once()
        self.assertEqual(self.publisher.publish.call_args[1]["kind"], "conversation.invalid_reply")

    def test_cross_job_reply_to_rejected(self):
        is_valid = validate_reply_to(
            reply_to="msg_other_job",
            thread_id="thread_alpha",
            conversation_id="conv_review",
            known_messages=self.known_messages,
            job_id="job_101",
            publisher=self.publisher,
        )
        self.assertFalse(is_valid)
        self.publisher.publish.assert_called_once()
        self.assertEqual(self.publisher.publish.call_args[1]["kind"], "conversation.invalid_reply")

    def test_cross_conversation_reply_to_rejected(self):
        is_valid = validate_reply_to(
            reply_to="msg_other_conv",
            thread_id="thread_alpha",
            conversation_id="conv_review",
            known_messages=self.known_messages,
            job_id="job_101",
            publisher=self.publisher,
        )
        self.assertFalse(is_valid)
        self.publisher.publish.assert_called_once()
        self.assertEqual(self.publisher.publish.call_args[1]["kind"], "conversation.invalid_reply")

    def test_none_or_empty_reply_to_passes(self):
        self.assertTrue(validate_reply_to(None, "thread_alpha", "conv_review", self.known_messages))
        self.assertTrue(validate_reply_to("", "thread_alpha", "conv_review", self.known_messages))

    def test_outgoing_message_with_invalid_reply_is_rejected_and_not_recorded(self):
        mod = _get_runner_module()
        HermesSprintRunner = mod.HermesSprintRunner

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            p1 = tmp_root / "p1.md"
            p1.write_text("Prompt 1", encoding="utf-8")

            spec_path = ROOT_DIR / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=False)
            runner.job_id = "job_inv_reply"
            runner.thread_id = "thread_job_inv_reply"
            runner.run_dir = tmp_root / "runs" / "test_inv"
            runner.run_dir.mkdir(parents=True, exist_ok=True)
            runner.messages_file = runner.run_dir / "messages.jsonl"
            runner.worktree_root = tmp_root / "worktrees"
            (runner.worktree_root / "worker").mkdir(parents=True, exist_ok=True)

            phase1 = {"name": "01_builder", "role": "builder", "agent": "gemini", "worktree_dir": "worker", "prompt_file": str(p1)}
            runner.spec["phases"] = [phase1]

            conv_id = "conv_inv_test"
            runner._record_message(
                from_actor={"id": "claude", "kind": "agent", "displayName": "Claude"},
                to_actors=[{"id": "gemini", "kind": "agent", "displayName": "Gemini"}],
                kind="a2a",
                intent="question",
                text="Initial question",
                conversation_id=conv_id,
            )

            # Gemini outputs structured reply referencing a NONEXISTENT replyTo
            def stub_exec(phase, wt, mailbox_messages=None, active_a2a_turn=None):
                return AgentTurnResult(
                    execution_result=None,
                    text="Output",
                    outgoing_messages=[
                        A2AOutput(
                            intent="answer",
                            to=["claude"],
                            text="Bad reply reference",
                            conversationId=conv_id,
                            replyTo="msg_completely_fake_999",
                        )
                    ]
                )

            runner.execute_agent = stub_exec
            runner.schedule_a2a_turns(phase1, runner.worktree_root / "worker", conversation_id=conv_id)

            # The invalid outgoing reply MUST NOT have been recorded into local_messages
            self.assertEqual(len(runner.local_messages), 1)  # Only the initial question exists


class TestPhase61TypeErrorSafety(unittest.TestCase):
    def test_internal_type_error_does_not_cause_double_execution(self):
        mod = _get_runner_module()
        HermesSprintRunner = mod.HermesSprintRunner

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            p1 = tmp_root / "p1.md"
            p1.write_text("Prompt 1", encoding="utf-8")

            spec_path = ROOT_DIR / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=False)
            runner.job_id = "job_type_err"
            runner.thread_id = "thread_job_type_err"
            runner.run_dir = tmp_root / "runs" / "test_err"
            runner.run_dir.mkdir(parents=True, exist_ok=True)
            runner.messages_file = runner.run_dir / "messages.jsonl"
            runner.worktree_root = tmp_root / "worktrees"
            (runner.worktree_root / "worker").mkdir(parents=True, exist_ok=True)

            phase1 = {"name": "01_builder", "role": "builder", "agent": "gemini", "worktree_dir": "worker", "prompt_file": str(p1)}
            runner.spec["phases"] = [phase1]

            conv_id = "conv_err_test"
            runner._record_message(
                from_actor={"id": "claude", "kind": "agent", "displayName": "Claude"},
                to_actors=[{"id": "gemini", "kind": "agent", "displayName": "Gemini"}],
                kind="a2a",
                intent="question",
                text="Question",
                conversation_id=conv_id,
            )

            call_count = 0

            def failing_exec(phase, wt, mailbox_messages=None, active_a2a_turn=None):
                nonlocal call_count
                call_count += 1
                # Raise an internal TypeError during agent execution
                raise TypeError("Internal logic bug inside adapter")

            runner.execute_agent = failing_exec
            runner.schedule_a2a_turns(phase1, runner.worktree_root / "worker", conversation_id=conv_id)

            # Execution was called exactly ONCE (not retried / double-run on TypeError)
            self.assertEqual(call_count, 1)


class TestPhase61TerminalIntentSemantics(unittest.TestCase):
    def test_terminal_intent_does_not_trigger_automatic_further_turn(self):
        mod = _get_runner_module()
        HermesSprintRunner = mod.HermesSprintRunner

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            p1 = tmp_root / "p1.md"
            p1.write_text("Prompt 1", encoding="utf-8")

            spec_path = ROOT_DIR / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=False)
            runner.job_id = "job_term_test"
            runner.thread_id = "thread_job_term_test"
            runner.run_dir = tmp_root / "runs" / "test_term"
            runner.run_dir.mkdir(parents=True, exist_ok=True)
            runner.messages_file = runner.run_dir / "messages.jsonl"
            runner.worktree_root = tmp_root / "worktrees"
            (runner.worktree_root / "worker").mkdir(parents=True, exist_ok=True)

            phase1 = {"name": "01_builder", "role": "builder", "agent": "gemini", "worktree_dir": "worker", "prompt_file": str(p1)}
            runner.spec["phases"] = [phase1]

            conv_id = "conv_term_test"
            # Seed a terminal intent message (review_result)
            runner._record_message(
                from_actor={"id": "claude", "kind": "agent", "displayName": "Claude"},
                to_actors=[{"id": "gemini", "kind": "agent", "displayName": "Gemini"}],
                kind="a2a",
                intent="review_result",
                text="Review completed and approved.",
                conversation_id=conv_id,
            )

            call_count = 0

            def dummy_exec(phase, wt, mailbox_messages=None, active_a2a_turn=None):
                nonlocal call_count
                call_count += 1
                return AgentTurnResult(execution_result=None, text="nothing", outgoing_messages=[])

            runner.execute_agent = dummy_exec
            runner.schedule_a2a_turns(phase1, runner.worktree_root / "worker", conversation_id=conv_id)

            # Terminal intent message does NOT trigger an automatic turn
            self.assertEqual(call_count, 0)


class TestPhase61RealA2AEndToEndExecutionLoop(unittest.TestCase):
    """
    ABSOLUTE ACCEPTANCE TEST:
    Verifies that raw provider stdout containing structured A2A output triggers production parsing,
    MessageDTO recording, and subsequent Hermes agent turn scheduling without monkeypatching _record_message.

    Sequence:
    1. Gemini (BUILD) seeds initial review_request -> Claude
    2. Claude executes and returns real stdout with structured correction_request
    3. Production parser extracts it -> Message recorded -> Gemini mailbox receives it
    4. Hermes scheduler selects Gemini for turn 2
    5. Gemini executes and returns real stdout with structured correction_result
    6. Production parser extracts it -> Message recorded -> Claude mailbox receives it
    7. Hermes scheduler selects Claude for turn 3
    8. Claude executes and returns terminal stdout with NO outgoing A2A block
    9. Conversation finishes cleanly, emitting conversation.completed!
    """

    def test_real_raw_stdout_to_scheduled_next_turn_loop(self):
        mod = _get_runner_module()
        HermesSprintRunner = mod.HermesSprintRunner

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            prompt1 = tmp_root / "p1.md"
            prompt1.write_text("Builder: Scaffold Redis store.\n", encoding="utf-8")
            prompt2 = tmp_root / "p2.md"
            prompt2.write_text("Hardener: Review Redis store.\n", encoding="utf-8")

            spec_path = ROOT_DIR / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=False)
            runner.job_id = "job_real_a2a_e2e"
            runner.thread_id = "thread_job_real_a2a_e2e"
            runner.run_dir = tmp_root / "runs" / "test_a2a_real"
            runner.run_dir.mkdir(parents=True, exist_ok=True)
            runner.messages_file = runner.run_dir / "messages.jsonl"
            runner.artifacts_file = runner.run_dir / "artifacts.json"
            runner.worktree_root = tmp_root / "worktrees"
            (runner.worktree_root / "worker").mkdir(parents=True, exist_ok=True)
            runner.limits["a2a"] = {
                "enabled": True,
                "max_turns_per_phase": 6,
                "max_turns_per_job": 12,
            }

            conv_id = "conv_production_review_01"

            # 1. Seed initial Gemini -> Claude review_request
            gemini_init_msg = runner._record_message(
                from_actor={"id": "gemini", "kind": "agent", "displayName": "Gemini"},
                to_actors=[{"id": "claude", "kind": "agent", "displayName": "Claude"}],
                kind="a2a",
                intent="review_request",
                text="BUILD complete. Commit 8a21fc9. Please review scheduler reset path.",
                conversation_id=conv_id,
            )

            execution_log = []

            # Mock agent backend execution (simulating subprocess stdout returned by providers)
            def stubbed_adapter_execute(context):
                agent_name = context.phase["agent"]
                execution_log.append({
                    "agent": agent_name,
                    "prompt": context.prompt,
                })

                # Claude's response on Turn 1: produces structured correction_request to Gemini
                if agent_name == "claude" and len(execution_log) == 1:
                    raw_stdout = f"""
Claude Review Analysis:
Checked mutex locks in scheduler.py.
Found that reset_state() does not acquire lock before clearing queue.

{LYSSTACK_A2A_START}
{{
  "intent": "correction_request",
  "to": ["gemini"],
  "text": "The reset_state() function must acquire the state lock prior to clearing queue.",
  "conversationId": "{conv_id}",
  "replyTo": "{gemini_init_msg['id']}",
  "correlationId": "corr_review_01"
}}
{LYSSTACK_A2A_END}
"""
                # Gemini's response on Turn 2: produces structured correction_result to Claude
                elif agent_name == "gemini" and len(execution_log) == 2:
                    claude_msg_id = runner.local_messages[-1]["id"]
                    raw_stdout = f"""
Gemini Fix Implementation:
Acquired mutex lock in reset_state(). Tests passing.

{LYSSTACK_A2A_START}
{{
  "intent": "correction_result",
  "to": ["claude"],
  "text": "Fixed in commit 91cf33a. Mutex acquired before queue clear.",
  "conversationId": "{conv_id}",
  "replyTo": "{claude_msg_id}",
  "correlationId": "corr_review_01"
}}
{LYSSTACK_A2A_END}
"""
                # Claude's response on Turn 3: verified, no further structured output
                elif agent_name == "claude" and len(execution_log) == 3:
                    raw_stdout = "Claude: Verified commit 91cf33a. Mutex lock correctly acquired. Review approved."
                else:
                    raw_stdout = "No action."

                return ExecutionResult(
                    command=[agent_name, "exec"],
                    returncode=0,
                    stdout=raw_stdout,
                    stderr="",
                    backend="subprocess",
                )

            # Register mock adapters that execute through standard runner flow
            mock_registry = MagicMock()
            mock_adapter = MagicMock()
            mock_adapter.execute.side_effect = stubbed_adapter_execute
            mock_registry.get.return_value = mock_adapter
            runner.agent_registry = mock_registry

            phase1 = {
                "name": "01_builder",
                "role": "builder",
                "agent": "gemini",
                "worktree_dir": "worker",
                "prompt_file": str(prompt1),
            }
            phase2 = {
                "name": "02_hardener",
                "role": "hardener",
                "agent": "claude",
                "worktree_dir": "worker",
                "prompt_file": str(prompt2),
            }
            runner.spec["phases"] = [phase1, phase2]

            # 2. Run real scheduler loop
            runner.schedule_a2a_turns(phase1, runner.worktree_root / "worker", conversation_id=conv_id)

            # 3. Assert complete turn sequence: Claude (Turn 1) -> Gemini (Turn 2) -> Claude (Turn 3)
            self.assertEqual(len(execution_log), 3)
            self.assertEqual(execution_log[0]["agent"], "claude")
            self.assertEqual(execution_log[1]["agent"], "gemini")
            self.assertEqual(execution_log[2]["agent"], "claude")

            # Verify prompt injection received active A2A turn sections
            self.assertIn("--- LYSSTACK ACTIVE A2A TURN ---", execution_log[0]["prompt"])
            self.assertIn("review_request", execution_log[0]["prompt"])
            self.assertIn("--- LYSSTACK ACTIVE A2A TURN ---", execution_log[1]["prompt"])
            self.assertIn("correction_request", execution_log[1]["prompt"])
            self.assertIn("--- LYSSTACK ACTIVE A2A TURN ---", execution_log[2]["prompt"])
            self.assertIn("correction_result", execution_log[2]["prompt"])

            # Verify recorded messages chain
            self.assertEqual(len(runner.local_messages), 3)  # init gemini msg + claude correction + gemini fix
            msg1 = runner.local_messages[0]
            msg2 = runner.local_messages[1]
            msg3 = runner.local_messages[2]

            self.assertEqual(msg2["from"]["id"], "claude")
            self.assertEqual(msg2["to"][0]["id"], "gemini")
            self.assertEqual(msg2["intent"], "correction_request")
            self.assertEqual(msg2["replyTo"], msg1["id"])
            self.assertEqual(msg2["conversationId"], conv_id)

            self.assertEqual(msg3["from"]["id"], "gemini")
            self.assertEqual(msg3["to"][0]["id"], "claude")
            self.assertEqual(msg3["intent"], "correction_result")
            self.assertEqual(msg3["replyTo"], msg2["id"])
            self.assertEqual(msg3["conversationId"], conv_id)


class TestPhase61RemoteMessageDiscovery(unittest.TestCase):
    def test_remote_control_plane_message_discovery_triggers_turn(self):
        mod = _get_runner_module()
        HermesSprintRunner = mod.HermesSprintRunner

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            p1 = tmp_root / "p1.md"
            p1.write_text("Prompt 1", encoding="utf-8")
            p2 = tmp_root / "p2.md"
            p2.write_text("Prompt 2", encoding="utf-8")

            spec_path = ROOT_DIR / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=False)
            runner.job_id = "job_remote_disc"
            runner.thread_id = "thread_job_remote_disc"
            runner.run_dir = tmp_root / "runs" / "test_remote"
            runner.run_dir.mkdir(parents=True, exist_ok=True)
            runner.messages_file = runner.run_dir / "messages.jsonl"
            runner.worktree_root = tmp_root / "worktrees"
            (runner.worktree_root / "worker").mkdir(parents=True, exist_ok=True)

            phase1 = {"name": "01_builder", "role": "builder", "agent": "gemini", "worktree_dir": "worker", "prompt_file": str(p1)}
            phase2 = {"name": "02_hardener", "role": "hardener", "agent": "claude", "worktree_dir": "worker", "prompt_file": str(p2)}
            runner.spec["phases"] = [phase1, phase2]

            # Remote inbox has a message, but runner.local_messages is EMPTY
            remote_msg = {
                "id": "msg_remote_001",
                "threadId": runner.thread_id,
                "jobId": runner.job_id,
                "from": {"id": "gemini", "kind": "agent", "displayName": "Gemini"},
                "to": [{"id": "claude", "kind": "agent", "displayName": "Claude"}],
                "kind": "a2a",
                "intent": "question",
                "text": "What is the recommended retry budget?",
                "conversationId": "conv_remote_sync",
            }
            remote_inbox_entry = {
                "messageId": "msg_remote_001",
                "recipientId": "claude",
                "state": "DELIVERED",
                "message": remote_msg,
            }

            mock_pub = MagicMock()
            mock_pub.enabled = True
            mock_pub.fetch_agent_inbox.side_effect = lambda agent_id, **kwargs: [remote_inbox_entry] if agent_id == "claude" else []

            orig_pub = mod.default_publisher
            mod.default_publisher = mock_pub

            executed_agents = []

            def stub_exec(phase, wt, mailbox_messages=None, active_a2a_turn=None):
                executed_agents.append(phase["agent"])
                return AgentTurnResult(execution_result=None, text="Answer: 3 retries.", outgoing_messages=[])

            runner.execute_agent = stub_exec

            try:
                # local_messages is empty
                self.assertEqual(len(runner.local_messages), 0)

                runner.schedule_a2a_turns(phase1, runner.worktree_root / "worker", conversation_id="conv_remote_sync")

                # Verify Claude was discovered and scheduled from remote inbox
                self.assertEqual(len(executed_agents), 1)
                self.assertEqual(executed_agents[0], "claude")

                # Verify message was acknowledged
                mock_pub.acknowledge_message.assert_called_with("claude", "msg_remote_001")
            finally:
                mod.default_publisher = orig_pub

    def test_remote_message_from_different_thread_is_ignored(self):
        """Verify remote thread scoping: messages from thread_B are ignored when runner is in thread_A."""
        mod = _get_runner_module()
        HermesSprintRunner = mod.HermesSprintRunner

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            p1 = tmp_root / "p1.md"
            p1.write_text("P1", encoding="utf-8")

            spec_path = ROOT_DIR / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=False)
            runner.job_id = "job_thread_A"
            runner.thread_id = "thread_job_thread_A"
            runner.run_dir = tmp_root / "runs" / "test_th"
            runner.run_dir.mkdir(parents=True, exist_ok=True)
            runner.messages_file = runner.run_dir / "messages.jsonl"
            runner.worktree_root = tmp_root / "worktrees"
            (runner.worktree_root / "worker").mkdir(parents=True, exist_ok=True)

            phase1 = {"name": "01_builder", "role": "builder", "agent": "gemini", "worktree_dir": "worker", "prompt_file": str(p1)}
            runner.spec["phases"] = [phase1]

            # Remote inbox has message belonging to ANOTHER thread
            remote_msg = {
                "id": "msg_cross_th_001",
                "threadId": "thread_DIFFERENT_B",
                "jobId": runner.job_id,
                "from": {"id": "claude", "kind": "agent", "displayName": "Claude"},
                "to": [{"id": "gemini", "kind": "agent", "displayName": "Gemini"}],
                "kind": "a2a",
                "intent": "question",
                "text": "Question from another thread",
                "conversationId": "conv_th_scope",
            }
            remote_inbox_entry = {
                "messageId": "msg_cross_th_001",
                "recipientId": "gemini",
                "state": "DELIVERED",
                "message": remote_msg,
            }

            mock_pub = MagicMock()
            mock_pub.enabled = True
            mock_pub.fetch_agent_inbox.side_effect = lambda agent_id, **kwargs: [remote_inbox_entry] if agent_id == "gemini" else []

            orig_pub = mod.default_publisher
            mod.default_publisher = mock_pub

            executed_agents = []

            def stub_exec(phase, wt, mailbox_messages=None, active_a2a_turn=None):
                executed_agents.append(phase["agent"])
                return AgentTurnResult(execution_result=None, text="Answer", outgoing_messages=[])

            runner.execute_agent = stub_exec

            try:
                runner.schedule_a2a_turns(phase1, runner.worktree_root / "worker", conversation_id="conv_th_scope")
                # Must NOT execute for cross-thread message
                self.assertEqual(len(executed_agents), 0)
            finally:
                mod.default_publisher = orig_pub


class TestPhase61NoCodeChangeConversationalTurn(unittest.TestCase):
    def test_pure_conversational_turn_succeeds_without_file_changes(self):
        """Verify that an A2A review/question turn does not fail on zero file modifications."""
        mod = _get_runner_module()
        HermesSprintRunner = mod.HermesSprintRunner

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            p = tmp_root / "p.md"
            p.write_text("Prompt", encoding="utf-8")

            spec_path = ROOT_DIR / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=False)
            runner.job_id = "job_no_code_change"
            runner.thread_id = "thread_job_no_code_change"
            runner.run_dir = tmp_root / "runs" / "test_no_code"
            runner.run_dir.mkdir(parents=True, exist_ok=True)
            runner.messages_file = runner.run_dir / "messages.jsonl"
            runner.worktree_root = tmp_root / "worktrees"
            (runner.worktree_root / "worker").mkdir(parents=True, exist_ok=True)

            phase = {"name": "02_hardener", "role": "hardener", "agent": "claude", "worktree_dir": "worker", "prompt_file": str(p)}
            runner.spec["phases"] = [phase]

            runner._record_message(
                from_actor={"id": "gemini", "kind": "agent", "displayName": "Gemini"},
                to_actors=[{"id": "claude", "kind": "agent", "displayName": "Claude"}],
                kind="a2a",
                intent="question",
                text="Is redis pool thread-safe?",
                conversation_id="conv_faq",
            )

            # Claude outputs pure explanation with ZERO file modifications
            def stub_exec(phase, wt, mailbox_messages=None, active_a2a_turn=None):
                return AgentTurnResult(
                    execution_result=None,
                    text=f"""
Claude response:
Yes, ConnectionPool handles connection synchronization.

{LYSSTACK_A2A_START}
{{
  "intent": "answer",
  "to": ["gemini"],
  "text": "Yes, ConnectionPool is thread-safe.",
  "conversationId": "conv_faq"
}}
{LYSSTACK_A2A_END}
""",
                    outgoing_messages=[
                        A2AOutput(intent="answer", to=["gemini"], text="Yes, ConnectionPool is thread-safe.", conversationId="conv_faq")
                    ],
                )

            runner.execute_agent = stub_exec

            # Must complete without raising FAILED_NO_CHANGES
            runner.schedule_a2a_turns(phase, runner.worktree_root / "worker", conversation_id="conv_faq")
            self.assertEqual(len(runner.local_messages), 2)
            self.assertEqual(runner.local_messages[1]["intent"], "answer")


class TestPhase61TurnLimits(unittest.TestCase):
    def test_turn_limit_halts_ping_pong_loop_and_emits_limit_reached(self):
        mod = _get_runner_module()
        HermesSprintRunner = mod.HermesSprintRunner

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            p1 = tmp_root / "p1.md"
            p1.write_text("P1", encoding="utf-8")
            p2 = tmp_root / "p2.md"
            p2.write_text("P2", encoding="utf-8")

            spec_path = ROOT_DIR / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=False)
            runner.job_id = "job_limit_test"
            runner.thread_id = "thread_job_limit_test"
            runner.run_dir = tmp_root / "runs" / "test_limit"
            runner.run_dir.mkdir(parents=True, exist_ok=True)
            runner.messages_file = runner.run_dir / "messages.jsonl"
            runner.worktree_root = tmp_root / "worktrees"
            (runner.worktree_root / "worker").mkdir(parents=True, exist_ok=True)
            runner.limits["a2a"] = {
                "enabled": True,
                "max_turns_per_phase": 3,
                "max_turns_per_job": 3,
            }

            phase1 = {"name": "01_builder", "role": "builder", "agent": "gemini", "worktree_dir": "worker", "prompt_file": str(p1)}
            phase2 = {"name": "02_hardener", "role": "hardener", "agent": "claude", "worktree_dir": "worker", "prompt_file": str(p2)}
            runner.spec["phases"] = [phase1, phase2]

            conv_id = "conv_infinite_ping_pong"

            runner._record_message(
                from_actor={"id": "gemini", "kind": "agent", "displayName": "Gemini"},
                to_actors=[{"id": "claude", "kind": "agent", "displayName": "Claude"}],
                kind="a2a",
                intent="question",
                text="Ping?",
                conversation_id=conv_id,
            )

            turn_count = 0

            def infinite_ping_pong(phase, wt, mailbox_messages=None, active_a2a_turn=None):
                nonlocal turn_count
                turn_count += 1
                curr = phase["agent"]
                other = "gemini" if curr == "claude" else "claude"
                out = A2AOutput(
                    intent="question",
                    to=[other],
                    text=f"Turn #{turn_count} from {curr}",
                    conversationId=conv_id,
                )
                return AgentTurnResult(execution_result=None, text="ping", outgoing_messages=[out])

            runner.execute_agent = infinite_ping_pong

            mock_pub = MagicMock()
            mock_pub.enabled = True
            orig_pub = mod.default_publisher
            mod.default_publisher = mock_pub

            try:
                runner.schedule_a2a_turns(phase1, runner.worktree_root / "worker", conversation_id=conv_id)

                # Exactly 3 turns should execute before hitting the phase limit of 3
                self.assertEqual(turn_count, 3)
                self.assertEqual(runner.job_a2a_turns, 3)

                # Verify conversation.limit_reached was published
                mock_pub.publish.assert_any_call(
                    source_id="hermes_runner",
                    source_kind="runtime",
                    kind="conversation.limit_reached",
                    detail="A2A conversation turn limit reached (3 turns)",
                    job_id="job_limit_test",
                    metadata={
                        "conversationId": conv_id,
                        "jobTurns": 3,
                        "maxJobTurns": 3,
                        "phaseTurns": 3,
                        "maxPhaseTurns": 3,
                    },
                )
            finally:
                mod.default_publisher = orig_pub


class TestPhase61PersonaLoaderRuntimeWiring(unittest.TestCase):
    def test_persona_loader_runtime_wiring_and_prompt_injection(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            card_path = Path(tmp_dir) / "elysia_card.json"
            card_path.write_text(json.dumps({
                "name": "Elysia",
                "summary": "Specialized architecture consultant and prompt designer.",
                "traits": ["thoughtful", "precise", "encouraging"],
                "speakingStyle": ["Speaks with clarity and warmth."],
                "behavioralRules": ["Verify system invariants before proposing refactors."],
                "permissions": ["sudo", "shell:all"],  # FORBIDDEN - MUST BE STRIPPED
                "tools": ["arbitrary_code_exec"],      # FORBIDDEN - MUST BE STRIPPED
            }), encoding="utf-8")

            # Resolve agent profile with character card path
            profile = resolve_agent_profile("elysia", custom_override=card_path)

            self.assertEqual(profile.id, "elysia")
            self.assertEqual(profile.displayName, "Elysia")
            self.assertIsNotNone(profile.persona)
            self.assertEqual(profile.persona.summary, "Specialized architecture consultant and prompt designer.")
            self.assertIn("thoughtful", profile.persona.traits)

            # Render prompt section and verify privilege keys are absent
            prompt_section = profile.persona.render_prompt_section("elysia", role="planner")
            self.assertIn("--- LYSSTACK AGENT IDENTITY ---", prompt_section)
            self.assertIn("Elysia (elysia)", prompt_section)
            self.assertIn("Speaks with clarity and warmth.", prompt_section)
            self.assertNotIn("sudo", prompt_section)
            self.assertNotIn("arbitrary_code_exec", prompt_section)


class TestPhase61CrossProcessSmoke(unittest.TestCase):
    """
    Real cross-process smoke test:
    Process A: Control Plane (FastAPI in background thread/process)
    Process B: Hermes Runner spawned as separate subprocess with LYSSTACK_CONTROL_URL
    """
    @classmethod
    def setUpClass(cls):
        from uvicorn import Config, Server
        import main
        import socket
        import time

        # Find open port
        sock = socket.socket()
        sock.bind(("", 0))
        cls.port = sock.getsockname()[1]
        sock.close()

        config = Config(app=main.app, host="127.0.0.1", port=cls.port, log_level="warning")
        cls.server = Server(config=config)
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()

        cls.control_url = f"http://127.0.0.1:{cls.port}"
        # Wait for server readiness
        for _ in range(50):
            try:
                with urllib.request.urlopen(f"{cls.control_url}/health", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True

    def test_real_cross_process_a2a_smoke_over_http(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            target_repo = tmp_path / "repo"
            target_repo.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=target_repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=target_repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=target_repo, check=True)
            (target_repo / "README.md").write_text("# Test\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=target_repo, check=True)
            subprocess.run(["git", "commit", "-m", "initial commit"], cwd=target_repo, check=True)

            p1_prompt = tmp_path / "p1.md"
            p1_prompt.write_text("Builder prompt\n", encoding="utf-8")
            p2_prompt = tmp_path / "p2.md"
            p2_prompt.write_text("Hardener prompt\n", encoding="utf-8")

            job_id = "run_p61_smoke"
            thread_id = f"thread_job_{job_id}"

            sprint_spec = {
                "sprint_id": "test-p61-smoke",
                "name": "Phase 6.1 Cross Process A2A Smoke Sprint",
                "target_repo": str(target_repo),
                "target_branch": "hermes/test-p61/integration",
                "worktree_root": str(tmp_path / "worktrees"),
                "runs_root": str(tmp_path / "runs"),
                "phases": [
                    {
                        "name": "01_builder",
                        "role": "builder",
                        "agent": "gemini",
                        "worktree_dir": "wt_builder",
                        "branch": "test-p61/builder",
                        "prompt_file": str(p1_prompt),
                        "expected_handoff": "HANDOFF_BUILD.md",
                        "commit_message": "feat: build complete",
                    },
                    {
                        "name": "02_hardener",
                        "role": "hardener",
                        "agent": "claude",
                        "worktree_dir": "wt_hardener",
                        "branch": "test-p61/hardener",
                        "prompt_file": str(p2_prompt),
                        "expected_handoff": "HANDOFF_HARDEN.md",
                        "commit_message": "fix: harden complete",
                    }
                ],
                "verification": [
                    {
                        "name": "check_target",
                        "command": [sys.executable, "-c", "print('Verified OK')"],
                        "timeout_seconds": 30
                    }
                ]
            }

            spec_file = tmp_path / "test-p61.json"
            spec_file.write_text(json.dumps(sprint_spec, indent=2), encoding="utf-8")

            # 1. Post initial Operator message targeted to Claude via Control Plane HTTP endpoint
            op_payload = json.dumps({
                "threadId": thread_id,
                "to": ["claude"],
                "kind": "operator",
                "intent": "operator_note",
                "text": "Please verify concurrency safety in state store."
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{self.control_url}/messages",
                data=op_payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 201)

            # 2. Run runner in separate subprocess
            runner_script = ROOT_DIR / "runner" / "run-hermes-sprint.py"
            driver_code = f"""
import sys
import json
from types import SimpleNamespace
from pathlib import Path
import importlib.util

spec = importlib.util.spec_from_file_location("run_hermes_sprint", "{runner_script}")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

runner = module.HermesSprintRunner(
    spec_path="{spec_file}",
    skip_agent_exec=False
)

def simulated_agent(phase, wt_dir, mailbox_messages=None, active_a2a_turn=None):
    agent_name = phase["agent"]
    (wt_dir / f"file_{{agent_name}}.py").write_text("# code\\n", encoding="utf-8")
    (wt_dir / phase["expected_handoff"]).write_text("# Handoff\\nSummary.\\n", encoding="utf-8")
    return SimpleNamespace(runtime_metadata={{}})

runner.execute_agent = simulated_agent
success = runner.execute()
sys.exit(0 if success else 1)
"""
            driver_file = tmp_path / "driver.py"
            driver_file.write_text(driver_code, encoding="utf-8")

            env = dict(os.environ)
            env["LYSSTACK_CONTROL_URL"] = self.control_url
            env["HERMES_JOB_ID"] = job_id

            run_proc = subprocess.run(
                [sys.executable, str(driver_file)],
                cwd=str(ROOT_DIR),
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(run_proc.returncode, 0, f"Runner failed:\n{run_proc.stdout}\n{run_proc.stderr}")

            # 3. Verify messages were delivered and recorded into Control Plane MessageStore
            with urllib.request.urlopen(f"{self.control_url}/threads/{thread_id}/messages") as resp:
                msgs = json.loads(resp.read().decode("utf-8"))
                self.assertGreater(len(msgs), 0)
                # Check for handoff message from builder
                handoff_msg = next((m for m in msgs if m.get("intent") == "review_request"), None)
                self.assertIsNotNone(handoff_msg)
                self.assertEqual(handoff_msg["from"]["id"], "gemini")


if __name__ == "__main__":
    unittest.main()
