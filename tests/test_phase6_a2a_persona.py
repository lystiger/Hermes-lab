import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from personas.persona import AgentProfile, PersonaProfile, PersonaVisual, resolve_agent_profile, DEFAULT_PERSONAS
from personas.persona_loader import PersonaLoader, FORBIDDEN_PRIVILEGE_KEYS
from messaging.message_store import ActorRefDTO, MessageDTO, ThreadDTO, MessageStore
from messaging.message_router import MessageRouter
from events.event_bus import RuntimeEventBus
import importlib.util
runner_script = ROOT_DIR / "runner" / "run-hermes-sprint.py"
spec = importlib.util.spec_from_file_location("run_hermes_sprint", str(runner_script))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
HermesSprintRunner = module.HermesSprintRunner
from main import app


class TestPhase6AgentProfileAndPersona(unittest.TestCase):
    def test_generic_agent_ids_supported_without_closed_unions(self):
        """Verify open string agent IDs work dynamically (e.g. elysia, kimi, qwen, planner_01)."""
        future_agents = ["elysia", "kimi", "qwen", "deepseek", "planner_01", "reviewer_02", "tool_git"]
        for aid in future_agents:
            profile = resolve_agent_profile(aid)
            self.assertEqual(profile.id, aid)
            self.assertEqual(profile.displayName, aid.capitalize())
            self.assertIsNotNone(profile.persona)
            self.assertEqual(profile.persona.name, aid.capitalize())

    def test_default_personas_characteristics(self):
        """Verify initial default personas for Gemini, Claude, Codex."""
        gemini = resolve_agent_profile("gemini")
        self.assertIn("energetic", gemini.persona.traits)
        self.assertIn("fast builder", gemini.persona.traits)
        self.assertEqual(gemini.persona.visual.subtitle, "Energetic Builder")

        claude = resolve_agent_profile("claude")
        self.assertIn("calm reviewer", claude.persona.traits)
        self.assertIn("hardener", claude.persona.traits)
        self.assertEqual(claude.persona.visual.subtitle, "Calm Hardener")

        codex = resolve_agent_profile("codex")
        self.assertIn("evidence-driven", codex.persona.traits)
        self.assertIn("precision", codex.persona.speakingStyle[0].lower())
        self.assertEqual(codex.persona.visual.subtitle, "Precision Verifier")

    def test_persona_loader_safe_parsing_and_fallback(self):
        """Verify character card safe loading, ignoring cosmetic fields, and fallback on malformed."""
        valid_card = {
            "name": "CustomElysia",
            "description": "High-throughput coordinator.",
            "personality": "meticulous, proactive",
            "speaking_style": "Clear concise instructions.\nDirect feedback.",
            "behavioral_rules": "Always check lint before commit.",
            "avatar": "/agents/elysia.png",
            "cosmetic_theme_color": "#FF00FF",  # unknown cosmetic field
        }
        loaded = PersonaLoader.load_from_dict(valid_card, fallback_name="Elysia")
        self.assertEqual(loaded.name, "CustomElysia")
        self.assertEqual(loaded.summary, "High-throughput coordinator.")
        self.assertEqual(loaded.traits, ["meticulous", "proactive"])
        self.assertEqual(len(loaded.speakingStyle), 2)
        self.assertEqual(loaded.visual.avatar, "/agents/elysia.png")

        # Malformed input -> safe fallback without crash
        malformed = {"name": None, "traits": 12345}
        fallback = PersonaLoader.load_from_dict(malformed, fallback_name="SafeFallback")
        self.assertEqual(fallback.name, "SafeFallback")
        self.assertIsNotNone(fallback.summary)

    def test_character_card_security_strips_privilege_grants(self):
        """Verify character cards cannot grant permissions, tools, shell access, or controller authority."""
        malicious_card = {
            "name": "Attacker",
            "description": "Attempts privilege escalation.",
            "permissions": ["root", "all-tools"],
            "shell": "/bin/bash",
            "sudo": True,
            "allowed_commands": ["rm -rf /"],
            "workspace_scope": "/",
        }
        sanitized = PersonaLoader.sanitize_untrusted_data(malicious_card)
        for key in FORBIDDEN_PRIVILEGE_KEYS:
            self.assertNotIn(key, sanitized)

        profile = PersonaLoader.load_from_dict(malicious_card)
        self.assertEqual(profile.name, "Attacker")
        # Ensure no permissions were attached
        self.assertFalse(hasattr(profile, "permissions"))
        self.assertFalse(hasattr(profile, "shell"))

    def test_prompt_precedence_and_identity_rendering(self):
        """Verify controller rules and truthfulness explicitly take precedence in persona prompt section."""
        persona = DEFAULT_PERSONAS["gemini"]
        rendered = persona.render_prompt_section(agent_id="gemini", role="builder")
        self.assertIn("--- LYSSTACK AGENT IDENTITY ---", rendered)
        self.assertIn("Agent: Gemini (gemini)", rendered)
        self.assertIn("Role: builder", rendered)
        self.assertIn("Controller rules, operator instructions, and workspace constraints strictly override persona style", rendered)
        self.assertIn("Remain technically truthful", rendered)
        self.assertIn("--- END AGENT IDENTITY ---", rendered)


class TestPhase6ExtendedMessageEnvelopeAndA2A(unittest.TestCase):
    def setUp(self):
        self.store = MessageStore()
        self.bus = RuntimeEventBus()
        self.router = MessageRouter(store=self.store, bus=self.bus)
        self.client = TestClient(app)

    def test_extended_message_envelope_fields_and_compatibility(self):
        """Verify conversationId, replyTo, correlationId on MessageDTO and backward compatibility."""
        # 1. Historical message without Phase 6 fields
        hist_dict = {
            "id": "msg_hist_01",
            "threadId": "thread_1",
            "from": {"id": "gemini", "kind": "agent"},
            "to": [{"id": "claude", "kind": "agent"}],
            "kind": "handoff",
            "text": "Old message without conversationId",
        }
        hist_msg = MessageDTO.from_dict(hist_dict)
        self.assertIsNone(hist_msg.conversationId)
        self.assertIsNone(hist_msg.replyTo)
        self.assertIsNone(hist_msg.correlationId)
        hist_exported = hist_msg.to_dict()
        self.assertIsNone(hist_exported["conversationId"])

        # 2. Phase 6 extended message
        p6_msg = self.router.send_message(
            thread_id="thread_job_101",
            from_actor="gemini",
            to_actors=["claude"],
            kind="a2a",
            text="Please review scheduler mutex lock implementation.",
            intent="review_request",
            conversation_id="conv_scheduler_rev",
            reply_to="msg_hist_01",
            correlation_id="corr_01",
            job_id="run_101",
        )
        self.assertEqual(p6_msg.conversationId, "conv_scheduler_rev")
        self.assertEqual(p6_msg.replyTo, "msg_hist_01")
        self.assertEqual(p6_msg.correlationId, "corr_01")

        # 3. List messages by conversationId
        conv_msgs = self.router.list_messages("thread_job_101", conversation_id="conv_scheduler_rev")
        self.assertEqual(len(conv_msgs), 1)
        self.assertEqual(conv_msgs[0].id, p6_msg.id)

    def test_open_string_a2a_intents_supported(self):
        """Verify standard and extensible open string intents work without closed enum restrictions."""
        intents = [
            "review_request",
            "review_result",
            "correction_request",
            "correction_result",
            "question",
            "answer",
            "verification_request",
            "verification_result",
            "operator_note",
            "custom_future_intent_x",
        ]
        for intent in intents:
            msg = self.router.send_message(
                thread_id="thread_intents",
                from_actor="agent_a",
                to_actors=["agent_b"],
                kind="a2a",
                text=f"Testing intent {intent}",
                intent=intent,
            )
            self.assertEqual(msg.intent, intent)

    def test_conversation_lifecycle_events_emitted(self):
        """Verify conversation.started and conversation.turn events are emitted."""
        msg = self.router.send_message(
            thread_id="thread_events",
            from_actor="gemini",
            to_actors=["claude"],
            kind="a2a",
            text="First message in conversation",
            conversation_id="conv_lifecycle_01",
            job_id="job_life",
        )

        recent_events = self.bus.recent(limit=50)
        event_kinds = [e.kind for e in recent_events]
        self.assertIn("conversation.started", event_kinds)
        self.assertIn("conversation.turn", event_kinds)
        turn_evt = next(e for e in recent_events if e.kind == "conversation.turn")
        self.assertEqual(turn_evt.metadata["conversationId"], "conv_lifecycle_01")
        self.assertEqual(turn_evt.metadata["messageId"], msg.id)


class TestPhase6HermesA2ATurnScheduler(unittest.TestCase):
    def test_hermes_scheduled_multi_agent_a2a_turn_loop(self):
        """
        Verify real Hermes A2A turn scheduling end-to-end:
        1. Gemini (BUILD) produces review_request -> Claude
        2. Claude (HARDEN) produces correction_request -> Gemini (replyTo: Gemini msg)
        3. Hermes schedules Gemini turn
        4. Gemini produces correction_result -> Claude (replyTo: Claude msg)
        5. Verify threadId, conversationId, replyTo chain, turn counts, and isolation.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            spec_path = ROOT_DIR / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=False)
            runner.job_id = "job_a2a_test"
            runner.thread_id = "thread_job_a2a_test"
            runner.run_dir = tmp_root / "runs" / "test_a2a"
            runner.run_dir.mkdir(parents=True, exist_ok=True)
            runner.messages_file = runner.run_dir / "messages.jsonl"
            runner.artifacts_file = runner.run_dir / "artifacts.json"
            runner.worktree_root = tmp_root / "worktrees"
            (runner.worktree_root / "worker").mkdir(parents=True, exist_ok=True)
            runner.limits["a2a"] = {
                "enabled": True,
                "max_turns_per_phase": 4,
                "max_turns_per_job": 10,
            }

            conv_id = "conv_scheduler_review_01"

            # 1. Gemini creates initial BUILD review_request
            gemini_msg = runner._record_message(
                from_actor={"id": "gemini", "kind": "agent", "displayName": "Gemini"},
                to_actors=[{"id": "claude", "kind": "agent", "displayName": "Claude"}],
                kind="a2a",
                intent="review_request",
                text="BUILD complete. Commit 8a21fc9. Please review scheduler state cleanup.",
                conversation_id=conv_id,
            )

            # Simulated agent execution tracker
            turn_executions = []

            def mock_execute_agent(phase, wt_dir, mailbox_messages=None):
                agent_name = phase["agent"]
                turn_executions.append({
                    "agent": agent_name,
                    "mailbox_count": len(mailbox_messages) if mailbox_messages else 0,
                    "mailbox": mailbox_messages or [],
                })

                # If Claude was scheduled in response to Gemini's review_request:
                if agent_name == "claude" and len(turn_executions) == 1:
                    # Claude reviews and replies with correction_request targeting Gemini
                    runner._record_message(
                        from_actor={"id": "claude", "kind": "agent", "displayName": "Claude"},
                        to_actors=[{"id": "gemini", "kind": "agent", "displayName": "Gemini"}],
                        kind="a2a",
                        intent="correction_request",
                        text="State cleanup race found in reset_state(). Please add mutex acquire before reset.",
                        conversation_id=conv_id,
                        reply_to=gemini_msg["id"],
                        correlation_id="corr_sched_01",
                    )
                # If Gemini was scheduled in response to Claude's correction_request:
                elif agent_name == "gemini" and len(turn_executions) == 2:
                    # Gemini fixes and replies with correction_result
                    claude_msg = runner.local_messages[-1]
                    runner._record_message(
                        from_actor={"id": "gemini", "kind": "agent", "displayName": "Gemini"},
                        to_actors=[{"id": "claude", "kind": "agent", "displayName": "Claude"}],
                        kind="a2a",
                        intent="correction_result",
                        text="Fixed in 91cf33a. Mutex acquired prior to reset_state().",
                        conversation_id=conv_id,
                        reply_to=claude_msg["id"],
                        correlation_id="corr_sched_01",
                    )

                return SimpleNamespace(runtime_metadata={})

            runner.execute_agent = mock_execute_agent

            phase1 = {
                "name": "01_builder",
                "role": "builder",
                "agent": "gemini",
                "worktree_dir": "worker",
                "prompt_file": str(ROOT_DIR / "prompts" / "s04-builder.md"),
            }
            phase2 = {
                "name": "02_hardener",
                "role": "hardener",
                "agent": "claude",
                "worktree_dir": "worker",
                "prompt_file": str(ROOT_DIR / "prompts" / "s04-hardener.md"),
            }
            runner.spec["phases"] = [phase1, phase2]

            # 2. Run schedule_a2a_turns
            runner.schedule_a2a_turns(phase1, runner.worktree_root / "worker", conversation_id=conv_id)

            # 3. Assertions
            # Turn 1: Claude executed (review_request)
            # Turn 2: Gemini executed (correction_request)
            # Turn 3: Claude executed (correction_result)
            self.assertEqual(len(turn_executions), 3)
            self.assertEqual(turn_executions[0]["agent"], "claude")
            self.assertEqual(turn_executions[1]["agent"], "gemini")
            self.assertEqual(turn_executions[2]["agent"], "claude")

            # Check message thread and replyTo chain
            self.assertEqual(len(runner.local_messages), 3)
            m1 = runner.local_messages[0]  # Gemini -> Claude (review_request)
            m2 = runner.local_messages[1]  # Claude -> Gemini (correction_request, replyTo: m1.id)
            m3 = runner.local_messages[2]  # Gemini -> Claude (correction_result, replyTo: m2.id)

            self.assertEqual(m1["conversationId"], conv_id)
            self.assertEqual(m2["conversationId"], conv_id)
            self.assertEqual(m3["conversationId"], conv_id)

            self.assertEqual(m2["replyTo"], m1["id"])
            self.assertEqual(m3["replyTo"], m2["id"])

            self.assertEqual(m2["correlationId"], "corr_sched_01")
            self.assertEqual(m3["correlationId"], "corr_sched_01")

            self.assertEqual(runner.job_a2a_turns, 3)

    def test_a2a_turn_limit_exhaustion_emits_event(self):
        """Verify when A2A turn limit is reached, scheduler halts and emits conversation.limit_reached."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            spec_path = ROOT_DIR / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=False)
            runner.job_id = "job_limit_test"
            runner.thread_id = "thread_job_limit_test"
            runner.run_dir = tmp_root / "runs" / "test_limit"
            runner.run_dir.mkdir(parents=True, exist_ok=True)
            runner.messages_file = runner.run_dir / "messages.jsonl"
            runner.artifacts_file = runner.run_dir / "artifacts.json"
            runner.worktree_root = tmp_root / "worktrees"
            (runner.worktree_root / "worker").mkdir(parents=True, exist_ok=True)

            # Configure strict limit: max 2 turns per phase
            runner.limits["a2a"] = {
                "enabled": True,
                "max_turns_per_phase": 2,
                "max_turns_per_job": 5,
            }

            phase1 = {
                "name": "01_builder",
                "role": "builder",
                "agent": "gemini",
                "worktree_dir": "worker",
                "prompt_file": str(ROOT_DIR / "prompts" / "s04-builder.md"),
            }
            phase2 = {
                "name": "02_hardener",
                "role": "hardener",
                "agent": "claude",
                "worktree_dir": "worker",
                "prompt_file": str(ROOT_DIR / "prompts" / "s04-hardener.md"),
            }
            runner.spec["phases"] = [phase1, phase2]

            conv_id = "conv_infinite_ping_pong"

            # Create initial message
            runner._record_message(
                from_actor={"id": "gemini", "kind": "agent"},
                to_actors=[{"id": "claude", "kind": "agent"}],
                kind="a2a",
                intent="question",
                text="Question 1",
                conversation_id=conv_id,
            )

            # Simulated endless loop agent
            def ping_pong_agent(phase, wt_dir, mailbox_messages=None):
                current = phase["agent"]
                next_target = "gemini" if current == "claude" else "claude"
                last_msg = runner.local_messages[-1]
                runner._record_message(
                    from_actor={"id": current, "kind": "agent"},
                    to_actors=[{"id": next_target, "kind": "agent"}],
                    kind="a2a",
                    intent="question",
                    text=f"Question from {current}",
                    conversation_id=conv_id,
                    reply_to=last_msg["id"],
                )
                return SimpleNamespace(runtime_metadata={})

            runner.execute_agent = ping_pong_agent

            events_emitted = []
            mock_publisher = MagicMock()
            mock_publisher.publish.side_effect = lambda **kwargs: events_emitted.append(kwargs)
            mock_publisher.enabled = False

            with unittest.mock.patch.object(module, "default_publisher", mock_publisher):
                runner.schedule_a2a_turns(phase1, runner.worktree_root / "worker", conversation_id=conv_id)

            # Verify turns stopped strictly at 2
            self.assertEqual(runner.job_a2a_turns, 2)
            limit_events = [e for e in events_emitted if e.get("kind") == "conversation.limit_reached"]
            self.assertTrue(len(limit_events) > 0)


if __name__ == "__main__":
    unittest.main()
