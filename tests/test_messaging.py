import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
import json
import tempfile
from pathlib import Path
import unittest
from fastapi.testclient import TestClient

from artifacts.artifact_registry import ArtifactRef, ArtifactRegistry
from messaging.message_store import ActorRefDTO, MessageDTO, ThreadDTO, MessageStore
from messaging.message_router import MessageRouter
from events.event_bus import RuntimeEventBus
from main import app


class TestArtifactRegistry(unittest.TestCase):
    def test_register_and_retrieve_artifacts(self):
        registry = ArtifactRegistry()
        art = ArtifactRef(
            id="art_001",
            type="git_commit",
            label="BUILD commit",
            ref="8a21fc9",
            jobId="run_101",
        )
        registry.register(art)
        retrieved = registry.get("art_001")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.ref, "8a21fc9")
        self.assertEqual(retrieved.type, "git_commit")

        job_arts = registry.list_for_job("run_101")
        self.assertEqual(len(job_arts), 1)
        self.assertEqual(job_arts[0].id, "art_001")

    def test_unknown_artifact_type_allowed_and_defaulted(self):
        registry = ArtifactRegistry()
        art = ArtifactRef(
            id="art_custom",
            type="custom_telemetry_dump",
            label="Custom Dump",
            ref="custom://data",
            jobId="run_102",
        )
        registry.register(art)
        self.assertEqual(registry.get("art_custom").type, "custom_telemetry_dump")

    def test_path_containment_and_traversal_prevention(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            allowed = Path(tmp_dir) / "safe_root"
            allowed.mkdir()
            safe_file = allowed / "safe.txt"
            safe_file.write_text("safe content")

            outside_file = Path(tmp_dir) / "secret.env"
            outside_file.write_text("SECRET=123")

            registry = ArtifactRegistry(allowed_roots=[allowed])
            self.assertTrue(registry.is_safe_path(str(safe_file)))
            self.assertFalse(registry.is_safe_path(str(outside_file)))
            self.assertFalse(registry.is_safe_path(str(allowed / ".." / "secret.env")))


class TestMessageStoreAndRouter(unittest.TestCase):
    def setUp(self):
        self.store = MessageStore()
        self.registry = ArtifactRegistry()
        self.bus = RuntimeEventBus()
        self.router = MessageRouter(store=self.store, registry=self.registry, bus=self.bus)

    def test_thread_creation_and_listing(self):
        thread = self.router.create_thread(
            thread_id="thread_job_run_1",
            job_id="run_1",
            title="Sprint 1 Execution",
            participants=["gemini", "claude", "codex"],
        )
        self.assertEqual(thread.id, "thread_job_run_1")
        self.assertEqual(len(thread.participants), 3)

        retrieved = self.router.get_thread("thread_job_run_1")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.jobId, "run_1")

        listed = self.router.list_threads(job_id="run_1")
        self.assertEqual(len(listed), 1)

        filtered_by_part = self.router.list_threads(participant="claude")
        self.assertEqual(len(filtered_by_part), 1)

        filtered_by_nonexistent = self.router.list_threads(participant="nonexistent")
        self.assertEqual(len(filtered_by_nonexistent), 0)

    def test_send_message_and_ordering(self):
        self.router.create_thread(
            thread_id="thread_job_run_1",
            job_id="run_1",
            participants=["gemini", "claude"],
        )

        msg1 = self.router.send_message(
            thread_id="thread_job_run_1",
            from_actor="gemini",
            to_actors=["claude"],
            kind="handoff",
            text="BUILD completed. Please review scheduler.",
            intent="review_request",
            job_id="run_1",
            artifact_refs=[
                {"id": "art_1", "type": "git_commit", "label": "commit 1", "ref": "sha1"}
            ],
        )

        msg2 = self.router.send_message(
            thread_id="thread_job_run_1",
            from_actor="claude",
            to_actors=["codex"],
            kind="handoff",
            text="HARDEN completed. Verification requested.",
            intent="verification_request",
            job_id="run_1",
        )

        messages = self.router.list_messages("thread_job_run_1")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].id, msg1.id)
        self.assertEqual(messages[1].id, msg2.id)
        self.assertEqual(messages[0].from_actor.id, "gemini")
        self.assertEqual(messages[0].to_actors[0].id, "claude")
        self.assertEqual(messages[0].intent, "review_request")
        self.assertEqual(len(messages[0].artifactRefs), 1)

    def test_mailbox_and_acknowledgment(self):
        self.router.send_message(
            thread_id="thread_1",
            from_actor="gemini",
            to_actors=["claude", "codex"],
            kind="handoff",
            text="Review requested",
        )

        claude_inbox = self.router.list_inbox("claude")
        self.assertEqual(len(claude_inbox), 1)
        self.assertEqual(claude_inbox[0].state, "DELIVERED")

        # Acknowledge message
        msg_id = claude_inbox[0].messageId
        acked = self.router.acknowledge(msg_id, "claude")
        self.assertTrue(acked)

        claude_inbox_after = self.router.list_inbox("claude", state="ACKNOWLEDGED")
        self.assertEqual(len(claude_inbox_after), 1)
        self.assertEqual(claude_inbox_after[0].state, "ACKNOWLEDGED")
        self.assertIsNotNone(claude_inbox_after[0].acknowledgedAt)

    def test_dynamic_agent_ids_supported(self):
        msg = self.router.send_message(
            thread_id="thread_dyn",
            from_actor="custom_agent_99",
            to_actors=["another_worker"],
            kind="status",
            text="Running custom workload",
        )
        self.assertEqual(msg.from_actor.id, "custom_agent_99")
        self.assertEqual(msg.to_actors[0].id, "another_worker")

    def test_persistence_recovery_from_runs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            runs_root = Path(tmp_dir)
            run_dir = runs_root / "20260822_lab-s04"
            run_dir.mkdir()
            msg_file = run_dir / "messages.jsonl"

            sample_msg = {
                "id": "msg_persisted_001",
                "threadId": "thread_job_run_persisted",
                "from": {"id": "gemini", "kind": "agent", "displayName": "Gemini"},
                "to": [{"id": "claude", "kind": "agent", "displayName": "Claude"}],
                "kind": "handoff",
                "text": "Persisted handoff message",
                "intent": "review_request",
                "jobId": "run_persisted",
                "artifactRefs": [{"id": "art_p1", "type": "git_commit", "label": "Commit", "ref": "abc1234"}],
                "createdAt": "2026-08-22T10:00:00Z",
            }
            msg_file.write_text(json.dumps(sample_msg) + "\n", encoding="utf-8")

            fresh_store = MessageStore()
            fresh_store.recover_from_runs(runs_root)

            messages = fresh_store.list_messages("thread_job_run_persisted")
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0].id, "msg_persisted_001")
            self.assertEqual(messages[0].text, "Persisted handoff message")


class TestControlApiMessagingEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_thread_and_messages_api_flow(self):
        # 1. Ingest thread from internal endpoint
        thread_res = self.client.post(
            "/internal/threads",
            json={
                "id": "thread_job_api_test",
                "jobId": "job_api_test",
                "title": "API Test Thread",
                "participants": [{"id": "gemini", "kind": "agent", "displayName": "Gemini"}],
            },
        )
        self.assertEqual(thread_res.status_code, 202)

        # 2. Ingest message
        msg_res = self.client.post(
            "/internal/messages",
            json={
                "threadId": "thread_job_api_test",
                "from": {"id": "gemini", "kind": "agent", "displayName": "Gemini"},
                "to": [{"id": "claude", "kind": "agent", "displayName": "Claude"}],
                "kind": "handoff",
                "text": "BUILD completed via internal ingress",
                "intent": "review_request",
                "jobId": "job_api_test",
                "artifactRefs": [
                    {"id": "art_test", "type": "git_commit", "label": "commit 123", "ref": "1234567"}
                ],
            },
        )
        self.assertEqual(msg_res.status_code, 202)

        # 3. GET /threads
        get_threads_res = self.client.get("/threads?jobId=job_api_test")
        self.assertEqual(get_threads_res.status_code, 200)
        threads_data = get_threads_res.json()
        self.assertTrue(any(t["id"] == "thread_job_api_test" for t in threads_data))

        # 4. GET /threads/{thread_id}
        get_thread_res = self.client.get("/threads/thread_job_api_test")
        self.assertEqual(get_thread_res.status_code, 200)
        self.assertEqual(get_thread_res.json()["jobId"], "job_api_test")

        # 5. GET /threads/{thread_id}/messages
        get_msgs_res = self.client.get("/threads/thread_job_api_test/messages")
        self.assertEqual(get_msgs_res.status_code, 200)
        msgs_data = get_msgs_res.json()
        self.assertEqual(len(msgs_data), 1)
        self.assertEqual(msgs_data[0]["text"], "BUILD completed via internal ingress")
        self.assertEqual(msgs_data[0]["artifactRefs"][0]["ref"], "1234567")

        # 6. POST /messages (Operator message)
        op_res = self.client.post(
            "/messages",
            json={
                "threadId": "thread_job_api_test",
                "to": ["claude"],
                "kind": "operator",
                "text": "Please verify state cleanup edge cases.",
            },
        )
        self.assertEqual(op_res.status_code, 201)
        op_data = op_res.json()
        self.assertEqual(op_data["from"]["id"], "operator")

        # 7. GET /agents/{agent_id}/inbox
        inbox_res = self.client.get("/agents/claude/inbox")
        self.assertEqual(inbox_res.status_code, 200)
        inbox_data = inbox_res.json()
        self.assertTrue(len(inbox_data) >= 2)


if __name__ == "__main__":
    unittest.main()


import importlib.util
from unittest.mock import MagicMock, patch
import subprocess

runner_path = Path(__file__).resolve().parent.parent / "runner" / "run-hermes-sprint.py"
spec = importlib.util.spec_from_file_location("run_hermes_sprint", runner_path)
runner_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner_module)
HermesSprintRunner = runner_module.HermesSprintRunner


class TestRunnerMessagingIntegration(unittest.TestCase):
    def setUp(self):
        self.logging_patch = patch.object(
            HermesSprintRunner, "_setup_logging", return_value=MagicMock()
        )
        self.logging_patch.start()
        self.addCleanup(self.logging_patch.stop)

    def test_runner_multi_phase_messaging_and_context_injection(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            spec_path = Path(__file__).resolve().parent.parent / "sprints" / "lab-s04.json"
            
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=True)
            runner.runs_root = tmp_root / "runs"
            runner.run_dir = tmp_root / "runs" / "test_run_01"
            runner.run_dir.mkdir(parents=True, exist_ok=True)
            runner.messages_file = runner.run_dir / "messages.jsonl"
            runner.artifacts_file = runner.run_dir / "artifacts.json"
            runner.worktree_root = tmp_root / "worktrees"
            (runner.worktree_root / "worker").mkdir(parents=True, exist_ok=True)
            (runner.worktree_root / "integration").mkdir(parents=True, exist_ok=True)

            p1_file = tmp_root / "p1.md"
            p1_file.write_text("Build prompt", encoding="utf-8")
            p2_file = tmp_root / "p2.md"
            p2_file.write_text("Harden prompt", encoding="utf-8")

            phase1 = {
                "name": "01_builder",
                "role": "builder",
                "agent": "gemini",
                "worktree_dir": "worker",
                "prompt_file": str(p1_file),
                "expected_handoff": "HANDOFF_BUILD.md",
                "commit_message": "feat: builder changes",
            }
            phase2 = {
                "name": "02_hardener",
                "role": "hardener",
                "agent": "claude",
                "worktree_dir": "worker",
                "prompt_file": str(p2_file),
                "expected_handoff": "HANDOFF_HARDEN.md",
                "commit_message": "fix: harden changes",
            }
            runner.spec["phases"] = [phase1, phase2]

            runner._prepare_handoff_path = MagicMock(return_value=(runner.worktree_root / "worker" / "HANDOFF_BUILD.md", None))
            runner._restore_handoff_path = MagicMock()
            runner.capture_handoff = MagicMock()
            runner.inspect_changed_files = MagicMock(return_value=["src/code.py"])
            runner.validate_python_syntax = MagicMock()
            runner.sync_phase_worktree = MagicMock()

            def command_result(command, **kwargs):
                stdout = "8a21fc9876543210\n" if command[:3] == ["git", "rev-parse", "HEAD"] else ""
                return subprocess.CompletedProcess(command, 0, stdout, "")

            runner.run_cmd = MagicMock(side_effect=command_result)

            # 1. Execute Phase 1 (BUILD by gemini)
            runner.execute_phase(phase1, phase_index=1)

            # Verify message 1 created
            self.assertEqual(len(runner.local_messages), 1)
            msg1 = runner.local_messages[0]
            self.assertEqual(msg1["from"]["id"], "gemini")
            self.assertEqual(msg1["to"][0]["id"], "claude")
            self.assertEqual(msg1["kind"], "handoff")
            self.assertEqual(msg1["intent"], "review_request")
            self.assertIn("8a21fc9", msg1["text"])
            self.assertTrue(runner.messages_file.exists())
            self.assertTrue(runner.artifacts_file.exists())

            # 2. Context Injection for Phase 2 (Claude)
            claude_prompt = runner.build_effective_prompt("Please harden the codebase.", current_agent="claude")
            self.assertIn("--- LYSSTACK OPERATIONAL THREAD ---", claude_prompt)
            self.assertIn("[from: gemini]", claude_prompt)
            self.assertIn("kind: handoff", claude_prompt)
            self.assertIn("intent: review_request", claude_prompt)
            self.assertIn("8a21fc9", claude_prompt)
            self.assertIn("--- END THREAD ---", claude_prompt)

            # 3. Execute Phase 2 (HARDEN by claude)
            runner.execute_phase(phase2, phase_index=2)
            self.assertEqual(len(runner.local_messages), 2)
            msg2 = runner.local_messages[1]
            self.assertEqual(msg2["from"]["id"], "claude")
            self.assertEqual(msg2["intent"], "verification_request")


class TestPhase51MailboxAndArtifactTrust(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.store = MessageStore()
        self.registry = ArtifactRegistry()
        self.bus = RuntimeEventBus()
        self.router = MessageRouter(store=self.store, registry=self.registry, bus=self.bus)

    def test_truthful_artifact_trust_validation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            allowed_root = Path(tmp_dir) / "hermes-runs"
            allowed_root.mkdir()
            safe_file = allowed_root / "HANDOFF_BUILD.md"
            safe_file.write_text("# Safe handoff", encoding="utf-8")

            outside_dir = Path(tmp_dir) / "external"
            outside_dir.mkdir()
            outside_file = outside_dir / "secret.key"
            outside_file.write_text("secret", encoding="utf-8")

            registry = ArtifactRegistry(allowed_roots=[allowed_root])

            # 1. Validated filesystem artifact contained in run root
            art_safe = ArtifactRef(
                id="art_safe",
                type="handoff",
                label="Handoff File",
                ref=str(safe_file),
            )
            registry.register(art_safe)
            self.assertEqual(art_safe.trust.status, "verified")
            self.assertEqual(art_safe.trust.kind, "path_containment")
            self.assertEqual(art_safe.trust.scope, "hermes_run_root")
            self.assertIn("Hermes run root", art_safe.trust.detail)

            # 2. Path traversal escape -> unverified
            art_escape = ArtifactRef(
                id="art_escape",
                type="log",
                label="Escape Log",
                ref=str(allowed_root / ".." / "external" / "secret.key"),
            )
            registry.register(art_escape)
            self.assertEqual(art_escape.trust.status, "unverified")
            self.assertEqual(art_escape.trust.kind, "path_containment")

            # 3. Relative path with .. traversal -> unverified
            art_rel_escape = ArtifactRef(
                id="art_rel_escape",
                type="file",
                label="Relative Traversal",
                ref="../../etc/passwd",
            )
            registry.register(art_rel_escape)
            self.assertEqual(art_rel_escape.trust.status, "unverified")

            # 4. Git commit reference -> containment N/A, git_reference
            art_commit = ArtifactRef(
                id="art_commit",
                type="git_commit",
                label="Commit SHA",
                ref="8a21fc9876543210",
            )
            registry.register(art_commit)
            self.assertEqual(art_commit.trust.status, "not_applicable")
            self.assertEqual(art_commit.trust.kind, "git_reference")
            self.assertEqual(art_commit.trust.detail, "Git commit reference")

    def test_operator_message_injected_into_target_agent_context(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            spec_path = Path(__file__).resolve().parent.parent / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=True)
            runner.job_id = "run_job_xyz"
            runner.thread_id = "thread_job_run_job_xyz"
            runner.run_dir = tmp_root / "runs" / "test_run"
            runner.run_dir.mkdir(parents=True, exist_ok=True)
            runner.messages_file = runner.run_dir / "messages.jsonl"
            runner.artifacts_file = runner.run_dir / "artifacts.json"
            runner.worktree_root = tmp_root / "worktrees"

            # Pre-seed an operator message addressed to claude for this job
            op_msg = {
                "id": "msg_op_001",
                "threadId": runner.thread_id,
                "from": {"id": "operator", "kind": "operator", "displayName": "Operator"},
                "to": [{"id": "claude", "kind": "agent", "displayName": "Claude"}],
                "kind": "operator",
                "intent": "operator_note",
                "text": "Please inspect scheduler mutex contention before modifying state.",
                "jobId": "run_job_xyz",
                "createdAt": "2026-08-22T10:00:00Z",
            }
            runner.local_messages.append(op_msg)

            # 1. Claude builds effective prompt -> message MUST be present
            claude_prompt = runner.build_effective_prompt("Base prompt for Claude.", current_agent="claude")
            self.assertIn("--- LYSSTACK OPERATIONAL MESSAGES FOR CLAUDE ---", claude_prompt)
            self.assertIn("[from: operator]", claude_prompt)
            self.assertIn("kind: operator", claude_prompt)
            self.assertIn("intent: operator_note", claude_prompt)
            self.assertIn("Please inspect scheduler mutex contention", claude_prompt)
            self.assertIn("--- END OPERATIONAL MESSAGES ---", claude_prompt)

            # 2. Another agent (e.g. codex) builds prompt -> message MUST NOT be injected
            codex_prompt = runner.build_effective_prompt("Base prompt for Codex.", current_agent="codex")
            self.assertNotIn("--- LYSSTACK OPERATIONAL MESSAGES FOR CODEX ---", codex_prompt)
            self.assertNotIn("Please inspect scheduler mutex contention", codex_prompt)

    def test_wrong_job_message_is_excluded(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            spec_path = Path(__file__).resolve().parent.parent / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=True)
            runner.job_id = "job_current"
            runner.thread_id = "thread_job_current"

            # Message belongs to different job
            wrong_job_msg = {
                "id": "msg_other_001",
                "threadId": "thread_job_other",
                "from": {"id": "operator", "kind": "operator", "displayName": "Operator"},
                "to": [{"id": "claude", "kind": "agent", "displayName": "Claude"}],
                "kind": "operator",
                "text": "Instruction for completely different job",
                "jobId": "job_other",
                "createdAt": "2026-08-22T10:00:00Z",
            }
            runner.local_messages.append(wrong_job_msg)

            claude_prompt = runner.build_effective_prompt("Base prompt", current_agent="claude")
            self.assertNotIn("Instruction for completely different job", claude_prompt)

    def test_mailbox_chronological_ordering(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            spec_path = Path(__file__).resolve().parent.parent / "sprints" / "lab-s04.json"
            runner = HermesSprintRunner(spec_path=spec_path, skip_agent_exec=True)
            runner.job_id = "job_order"
            runner.thread_id = "thread_job_order"

            msg1 = {
                "id": "msg_001",
                "threadId": runner.thread_id,
                "from": {"id": "operator", "kind": "operator"},
                "to": [{"id": "claude"}],
                "kind": "operator",
                "text": "FIRST instruction",
                "jobId": "job_order",
                "createdAt": "2026-08-22T10:00:01Z",
            }
            msg2 = {
                "id": "msg_002",
                "threadId": runner.thread_id,
                "from": {"id": "operator", "kind": "operator"},
                "to": [{"id": "claude"}],
                "kind": "operator",
                "text": "SECOND guidance",
                "jobId": "job_order",
                "createdAt": "2026-08-22T10:00:02Z",
            }
            msg3 = {
                "id": "msg_003",
                "threadId": runner.thread_id,
                "from": {"id": "operator", "kind": "operator"},
                "to": [{"id": "claude"}],
                "kind": "operator",
                "text": "THIRD guidance",
                "jobId": "job_order",
                "createdAt": "2026-08-22T10:00:03Z",
            }
            # Insert in scrambled order
            runner.local_messages.extend([msg3, msg1, msg2])

            claude_prompt = runner.build_effective_prompt("Base prompt", current_agent="claude")
            pos1 = claude_prompt.find("FIRST instruction")
            pos2 = claude_prompt.find("SECOND guidance")
            pos3 = claude_prompt.find("THIRD guidance")

            self.assertTrue(pos1 != -1 and pos2 != -1 and pos3 != -1)
            self.assertTrue(pos1 < pos2 < pos3, "Messages were not formatted in chronological order")

    def test_acknowledgement_api_and_mailbox_state(self):
        # 1. Post operator message via control API
        msg_resp = self.client.post(
            "/messages",
            json={
                "threadId": "thread_ack_test",
                "to": ["claude"],
                "kind": "operator",
                "text": "Please check error handling",
            },
        )
        self.assertEqual(msg_resp.status_code, 201)
        msg_data = msg_resp.json()
        msg_id = msg_data["id"]

        # 2. Verify message in Claude inbox with DELIVERED state
        inbox_resp = self.client.get("/agents/claude/inbox?state=DELIVERED")
        self.assertEqual(inbox_resp.status_code, 200)
        inbox = inbox_resp.json()
        entry = next((e for e in inbox if e["messageId"] == msg_id), None)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["state"], "DELIVERED")

        # 3. Acknowledge message via POST /agents/claude/inbox/{msg_id}/ack
        ack_resp = self.client.post(f"/agents/claude/inbox/{msg_id}/ack")
        self.assertEqual(ack_resp.status_code, 200)
        self.assertTrue(ack_resp.json()["acknowledged"])

        # 4. Verify message in ACKNOWLEDGED state
        acked_inbox = self.client.get("/agents/claude/inbox?state=ACKNOWLEDGED").json()
        acked_entry = next((e for e in acked_inbox if e["messageId"] == msg_id), None)
        self.assertIsNotNone(acked_entry)
        self.assertEqual(acked_entry["state"], "ACKNOWLEDGED")
