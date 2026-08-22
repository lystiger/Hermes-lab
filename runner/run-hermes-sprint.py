#!/usr/bin/env python3
"""
Hermes Sprint Runner
Controller script for managing multi-agent sprint workflows, worktrees, git operations,
agent execution, fail-fast validations, and automated test validation.

Governance Boundaries:
- Control root: Hermes repository containing runner, prompts, and reports.
- Target repo: configured Git repository being changed (must be clean).
- Worktrees: configured target-repository worktree root.
- Runs/Logs: configured Hermes runtime storage.
- Git operations are strictly controller-owned. Agents edit files only.
- Does NOT push to remote, merge to main, or access production resources.
"""

import sys
import json
import argparse
import subprocess
import py_compile
import logging
import os
from pathlib import Path, PureWindowsPath
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from agents.base import AgentContext
from agents.errors import SprintRunnerError
from agents.permissions import scoped_antigravity_permissions
from agents.registry import default_registry
from backends.registry import default_backend_registry
from control_plane.event_publisher import default_publisher

ROOT_DIR = SCRIPT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from artifact_registry import artifact_registry, ArtifactRef, ArtifactTrust
    from normalization import normalize_agent_id
    from persona import resolve_agent_profile, PersonaProfile, AgentProfile
    from capabilities import CapabilityRegistry, Capability, CapabilityRef, create_default_capability_registry, DEFAULT_CAPABILITY_PROFILES
    from delegation import DelegationRequest, DelegationDecision, TaskAssignment, LYSSTACK_DELEGATION_START, LYSSTACK_DELEGATION_END
    from tools import ToolProfile, ToolInvocationRequest, ToolInvocationResult, ToolRegistry, default_tool_registry, LYSSTACK_TOOL_REQUEST_START, LYSSTACK_TOOL_REQUEST_END
    from subagents import SubagentProfile, SubagentManager
    from a2a import (
        A2AOutput,
        AgentTurnResult,
        parse_a2a_output,
        validate_reply_to,
        SCHEDULABLE_INTENTS,
        TERMINAL_INTENTS,
        LYSSTACK_A2A_START,
        LYSSTACK_A2A_END,
    )
except ImportError:
    artifact_registry = None
    ArtifactRef = None
    ArtifactTrust = None
    normalize_agent_id = lambda x: str(x).lower()
    resolve_agent_profile = None
    PersonaProfile = None
    AgentProfile = None
    A2AOutput = None
    AgentTurnResult = None
    parse_a2a_output = None
    validate_reply_to = None
    SCHEDULABLE_INTENTS = {"review_request", "correction_request", "question", "verification_request"}
    TERMINAL_INTENTS = {"review_result", "correction_result", "answer", "verification_result", "status"}
    LYSSTACK_A2A_START = "--- LYSSTACK A2A OUTPUT ---"
    LYSSTACK_A2A_END = "--- END LYSSTACK A2A OUTPUT ---" 


class HermesSprintRunner:
    PHASE_ROLES = {"builder", "hardener", "verifier"}
    DEFAULT_CONTEXT_MAX_BYTES = 256 * 1024

    def __init__(
        self,
        spec_path,
        dry_run=False,
        skip_agent_exec=False,
        verbose=False,
        agent_registry=None,
        backend_registry=None,
        backend_override=None,
        export_report=False,
    ):
        self.spec_path = Path(spec_path).resolve()
        self.dry_run = dry_run
        self.skip_agent_exec = skip_agent_exec
        self.verbose = verbose
        self.agent_registry = agent_registry or default_registry
        self.backend_registry = backend_registry or default_backend_registry
        self.backend_override = backend_override
        
        self.spec = self._load_spec()
        self.sprint_id = self.spec.get("sprint_id", "lab-s02")
        self.control_root = self._resolve_config_path(
            self.spec.get("control_root"),
            default=SCRIPT_DIR.parent,
        )
        self.target_repo = self._resolve_config_path(
            self.spec.get("target_repo") or self.spec.get("canonical_repo"),
            default=self.control_root,
        )
        default_storage_root = self.control_root.parent
        self.worktree_root = self._resolve_config_path(
            self.spec.get("worktree_root"),
            default=default_storage_root / "hermes-worktrees" / self.sprint_id,
        )
        self.runs_root = self._resolve_config_path(
            self.spec.get("runs_root"),
            default=default_storage_root / "hermes-runs",
        )
        self.limits = self.spec.get("limits", {"max_changed_files": 15, "timeout_seconds": 300})
        self.context_root = None
        self.context_files = []
        self.context_bundle = ""
        self.context_bytes = 0
        self._load_context_bundle()
        self.verification_steps = self._load_verification_spec()
        self._validate_phase_roles()
        self._validate_phase_permissions()
        if export_report is True:
            self.report_path = (
                self.control_root / "reports" / self.sprint_id / "run-summary.json"
            )
        elif export_report:
            self.report_path = Path(export_report).resolve()
        else:
            self.report_path = None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = self.runs_root / f"{timestamp}_{self.sprint_id}"
        self.log_file = self.run_dir / "runner.log"
        self.summary_file = self.run_dir / "run_summary.json"
        self.job_id = os.environ.get("HERMES_JOB_ID") or f"run_{timestamp}_{self.sprint_id}"
        self._backend_cache = {}
        self.thread_id = f"thread_job_{self.job_id}"
        self.local_messages = []
        self.local_artifacts = []
        self.messages_file = self.run_dir / "messages.jsonl"
        self.artifacts_file = self.run_dir / "artifacts.json"
        self._consumed_message_ids = set()
        self.job_a2a_turns = 0
        self.capability_registry = create_default_capability_registry()
        self.tool_registry = default_tool_registry
        delegation_limits = self.limits.get("delegation", {}) if isinstance(self.limits.get("delegation"), dict) else {}
        self.subagent_manager = SubagentManager(
            allow_subagents=delegation_limits.get("allow_subagents", False),
            max_subagents_per_job=delegation_limits.get("max_subagents_per_job", 3),
            max_depth=delegation_limits.get("max_depth", 1),
            allowed_capabilities=delegation_limits.get("allowed_capabilities") or delegation_limits.get("allowed_subagent_capabilities"),
        )
        self.task_assignments = {}
        self.job_delegations = 0
        persona_spec = self.spec.get("persona")
        if isinstance(persona_spec, dict):
            self.persona_enabled = persona_spec.get("enabled", True)
        elif persona_spec is not None:
            self.persona_enabled = bool(persona_spec)
        else:
            sprint_id = str(self.spec.get("sprint_id", "")).lower()
            spec_file_name = self.spec_path.name.lower()
            self.persona_enabled = bool(
                any("persona" in p for p in self.spec.get("phases", []))
                or "persona" in self.spec
                or "a2a" in self.spec
                or "s06" in sprint_id
                or "p6" in sprint_id
                or "persona" in spec_file_name
                or "a2a" in spec_file_name
                or "s06" in spec_file_name
            )
        
        self.logger = self._setup_logging()
        self.run_summary = {
            "sprint_id": self.sprint_id,
            "start_time": datetime.now().isoformat(),
            "status": "INITIALIZING",
            "phases": [],
            "test_results": None,
            "verification_status": None,
            "verification_results": [],
            "integration_commit": None,
            "errors": []
        }
        if self.context_files:
            self.run_summary["context"] = {
                "files_count": len(self.context_files),
                "bytes": self.context_bytes,
            }

    def _load_spec(self):
        if not self.spec_path.exists():
            raise FileNotFoundError(f"Sprint specification file not found: {self.spec_path}")
        with open(self.spec_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _resolve_config_path(self, value, *, default):
        """Resolve configured paths relative to the sprint specification directory."""
        path = Path(value) if value is not None else Path(default)
        if not path.is_absolute():
            path = self.spec_path.parent / path
        return path.resolve()

    def resolve_prompt_file(self, phase):
        prompt_file = Path(phase["prompt_file"])
        if not prompt_file.is_absolute():
            prompt_file = self.control_root / prompt_file
        return prompt_file.resolve()

    def _load_context_bundle(self):
        if "context" not in self.spec:
            return
        context = self.spec["context"]
        if not isinstance(context, dict):
            self._invalid_context("'context' must be a JSON object")

        root_value = context.get("root")
        if not isinstance(root_value, str) or not root_value.strip():
            self._invalid_context("context.root must be a non-empty path string")
        root_path = Path(root_value)
        if not root_path.is_absolute():
            if PureWindowsPath(root_value).anchor:
                self._invalid_context(
                    "context.root must use a path native to the current platform"
                )
            root_path = self.spec_path.parent / root_path
        root_path = root_path.resolve()
        if not root_path.is_dir():
            self._invalid_context(
                f"context.root does not exist or is not a directory: {root_value}"
            )

        files = context.get("files")
        if (
            not isinstance(files, list)
            or not files
            or any(not isinstance(item, str) or not item.strip() for item in files)
        ):
            self._invalid_context(
                "context.files must be a non-empty array of non-empty strings"
            )

        max_bytes = context.get("max_bytes", self.DEFAULT_CONTEXT_MAX_BYTES)
        if (
            isinstance(max_bytes, bool)
            or not isinstance(max_bytes, int)
            or max_bytes <= 0
        ):
            self._invalid_context("context.max_bytes must be a positive integer")

        loaded_files = []
        seen_paths = set()
        total_bytes = 0
        for file_value in files:
            native_path = Path(file_value)
            windows_path = PureWindowsPath(file_value)
            if (
                native_path.is_absolute()
                or windows_path.anchor
                or ".." in windows_path.parts
            ):
                self._invalid_context(
                    f"context file must be relative and contained: {file_value}"
                )

            resolved_path = (root_path / native_path).resolve()
            try:
                resolved_path.relative_to(root_path)
            except ValueError as error:
                raise SprintRunnerError(
                    "FAILED_INVALID_CONTEXT_SPEC",
                    f"Context file escapes context.root: {file_value}",
                ) from error
            if resolved_path in seen_paths:
                self._invalid_context(
                    f"duplicate normalized context file: {file_value}"
                )
            seen_paths.add(resolved_path)

            if not resolved_path.exists():
                raise SprintRunnerError(
                    "FAILED_CONTEXT_FILE_MISSING",
                    f"Context file does not exist: {file_value}",
                )
            if not resolved_path.is_file():
                raise SprintRunnerError(
                    "FAILED_CONTEXT_FILE_INVALID",
                    f"Context entry is not a regular file: {file_value}",
                )
            try:
                content = resolved_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                raise SprintRunnerError(
                    "FAILED_CONTEXT_READ",
                    f"Unable to read UTF-8 context file: {file_value}",
                ) from error

            total_bytes += len(content.encode("utf-8"))
            if total_bytes > max_bytes:
                raise SprintRunnerError(
                    "FAILED_CONTEXT_TOO_LARGE",
                    f"Context bundle exceeds max_bytes while loading: {file_value}",
                )
            logical_name = resolved_path.relative_to(root_path).as_posix()
            loaded_files.append((logical_name, content))

        sections = ["--- HERMES CONTEXT BUNDLE ---"]
        for logical_name, content in loaded_files:
            sections.append(f"[context: {logical_name}]\n{content}")
        sections.append("--- END HERMES CONTEXT BUNDLE ---")

        self.context_root = root_path
        self.context_files = loaded_files
        self.context_bytes = total_bytes
        self.context_bundle = "\n\n".join(sections)

    @staticmethod
    def _invalid_context(message):
        raise SprintRunnerError("FAILED_INVALID_CONTEXT_SPEC", message)

    def _record_artifact(self, artifact_dict):
        if "trust" not in artifact_dict and artifact_registry and ArtifactRef:
            try:
                if hasattr(self, "canonical_repo") and self.canonical_repo:
                    artifact_registry.add_allowed_root(self.canonical_repo)
                if hasattr(self, "runs_root") and self.runs_root:
                    artifact_registry.add_allowed_root(self.runs_root)
                if hasattr(self, "worktree_root") and self.worktree_root:
                    artifact_registry.add_allowed_root(self.worktree_root)

                ref_obj = ArtifactRef.from_dict(artifact_dict)
                trust_obj = artifact_registry.validate_artifact_trust(ref_obj)
                artifact_dict["trust"] = trust_obj.to_dict()
            except Exception as e:
                self.logger.debug("Failed to evaluate artifact trust: %s", e)

        self.local_artifacts.append(artifact_dict)
        try:
            self.artifacts_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.artifacts_file, "w", encoding="utf-8") as f:
                json.dump(self.local_artifacts, f, indent=2)
        except Exception as exc:
            self.logger.warning("Failed writing artifacts.json: %s", exc)

        if default_publisher:
            default_publisher.publish_artifact(artifact_dict)
        return artifact_dict

    def _record_message(
        self,
        from_actor,
        to_actors,
        kind,
        text,
        intent=None,
        phase_id=None,
        conversation_id=None,
        reply_to=None,
        correlation_id=None,
        artifact_refs=None,
        metadata=None,
    ):
        now_iso = datetime.now().isoformat()
        ts_ms = int(datetime.now().timestamp() * 1000)
        msg_id = f"msg_{ts_ms}_{len(self.local_messages) + 1:04d}"

        msg_dict = {
            "id": msg_id,
            "threadId": self.thread_id,
            "from": from_actor,
            "to": to_actors,
            "kind": kind,
            "text": text,
            "intent": intent,
            "conversationId": conversation_id,
            "replyTo": reply_to,
            "correlationId": correlation_id,
            "jobId": self.job_id,
            "phaseId": phase_id,
            "artifactRefs": artifact_refs or [],
            "metadata": metadata or {},
            "createdAt": now_iso,
        }

        self.local_messages.append(msg_dict)
        try:
            self.messages_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.messages_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(msg_dict) + "\n")
        except Exception as exc:
            self.logger.warning("Failed appending to messages.jsonl: %s", exc)

        if default_publisher:
            default_publisher.publish_message(
                thread_id=self.thread_id,
                from_actor=from_actor,
                to_actors=to_actors,
                kind=kind,
                text=text,
                intent=intent,
                conversation_id=conversation_id,
                reply_to=reply_to,
                correlation_id=correlation_id,
                job_id=self.job_id,
                phase_id=phase_id,
                artifact_refs=artifact_refs,
                metadata=metadata,
            )
        return msg_dict

    def build_operational_thread_section(self, current_agent=None):
        if not self.local_messages:
            return ""

        valid_thread_msgs = []
        for msg in self.local_messages:
            job_match = (
                (msg.get("jobId") == self.job_id)
                or (msg.get("threadId") == self.thread_id)
                or (not msg.get("jobId") and not msg.get("threadId"))
            )
            if not job_match:
                continue
            # Thread-level handoffs and results belong to general thread history
            if msg.get("kind") in {"handoff", "verification_result", "phase_failure", "status"}:
                valid_thread_msgs.append(msg)

        if not valid_thread_msgs:
            return ""

        valid_thread_msgs.sort(key=lambda m: m.get("createdAt") or m.get("id") or "")

        sections = ["--- LYSSTACK OPERATIONAL THREAD ---"]
        for msg in valid_thread_msgs:
            from_id = msg.get("from", {}).get("id", "unknown") if isinstance(msg.get("from"), dict) else str(msg.get("from"))
            kind = msg.get("kind", "status")
            intent = msg.get("intent")
            text = msg.get("text", "")
            artifacts = msg.get("artifactRefs", [])

            header = f"[from: {from_id}]\nkind: {kind}"
            if intent:
                header += f"\nintent: {intent}"
            if msg.get("conversationId"):
                header += f"\nconversation: {msg.get('conversationId')}"
            if msg.get("replyTo"):
                header += f"\nreplyTo: {msg.get('replyTo')}"
            body = f"{header}\n\n{text}"
            if artifacts:
                art_lines = ["\nArtifacts:"]
                for art in artifacts:
                    art_lines.append(f"- {art.get('type', 'generic')}: {art.get('ref', '')} ({art.get('label', '')})")
                body += "\n".join(art_lines)

            sections.append(body)

        sections.append("--- END THREAD ---")
        return "\n\n".join(sections)

    def fetch_pending_mailbox_messages(self, current_agent):
        norm_agent = normalize_agent_id(current_agent) if normalize_agent_id else str(current_agent).lower()
        consumed = getattr(self, "_consumed_message_ids", set())
        messages_by_id = {}

        # 1. Fetch remote messages from control plane inbox
        if default_publisher and default_publisher.enabled:
            remote_entries = default_publisher.fetch_agent_inbox(
                agent_id=current_agent,
                state="DELIVERED",
                job_id=self.job_id,
                thread_id=self.thread_id,
            )
            for entry in remote_entries:
                msg = entry.get("message")
                if msg and isinstance(msg, dict):
                    msg_id = msg.get("id")
                    to_list = msg.get("to", [])
                    recipient_matches = any(
                        (t.get("id") if isinstance(t, dict) else str(t)).lower() in {norm_agent, str(current_agent).lower()}
                        for t in to_list
                    )
                    job_matches = (
                        (msg.get("jobId") == self.job_id)
                        or (msg.get("threadId") == self.thread_id)
                        or (not msg.get("jobId") and not msg.get("threadId"))
                    )
                    if msg_id and msg_id not in consumed and recipient_matches and job_matches:
                        messages_by_id[msg_id] = msg

        # 2. Check local messages recorded in this runner
        for msg in self.local_messages:
            msg_id = msg.get("id")
            if not msg_id or msg_id in consumed:
                continue
            to_list = msg.get("to", [])
            recipient_matches = any(
                (t.get("id") if isinstance(t, dict) else str(t)).lower() in {norm_agent, str(current_agent).lower()}
                for t in to_list
            )
            job_matches = (msg.get("jobId") == self.job_id) or (msg.get("threadId") == self.thread_id)
            if recipient_matches and job_matches:
                messages_by_id[msg_id] = msg

        result = list(messages_by_id.values())
        result.sort(key=lambda m: m.get("createdAt") or m.get("id") or "")
        return result

    def build_mailbox_messages_section(self, current_agent, mailbox_messages):
        if not mailbox_messages:
            return ""

        sections = [f"--- LYSSTACK OPERATIONAL MESSAGES FOR {str(current_agent).upper()} ---"]
        for msg in mailbox_messages:
            from_obj = msg.get("from", {})
            from_id = from_obj.get("id", "unknown") if isinstance(from_obj, dict) else str(from_obj)
            kind = msg.get("kind", "operator")
            intent = msg.get("intent")
            text = msg.get("text", "")
            artifacts = msg.get("artifactRefs", [])

            header = f"[from: {from_id}]\nkind: {kind}"
            if intent:
                header += f"\nintent: {intent}"
            if msg.get("conversationId"):
                header += f"\nconversation: {msg.get('conversationId')}"
            if msg.get("replyTo"):
                header += f"\nreplyTo: {msg.get('replyTo')}"
            if msg.get("correlationId"):
                header += f"\ncorrelationId: {msg.get('correlationId')}"
            body = f"{header}\n\n{text}"
            if artifacts:
                art_lines = ["\nArtifacts:"]
                for art in artifacts:
                    art_lines.append(f"- {art.get('type', 'generic')}: {art.get('ref', '')} ({art.get('label', '')})")
                body += "\n".join(art_lines)

            sections.append(body)

        sections.append("--- END OPERATIONAL MESSAGES ---")
        return "\n\n".join(sections)

    def build_effective_prompt(self, base_prompt, current_agent=None, mailbox_messages=None, role=None, active_a2a_turn=None):
        parts = []

        # 1. Agent Identity & Persona section
        if current_agent and getattr(self, "persona_enabled", False) and resolve_agent_profile:
            role_name = role or "operative"
            try:
                # Check for character card override in spec
                char_override = None
                if isinstance(getattr(self, "spec", None), dict) and isinstance(self.spec.get("character_cards"), dict):
                    char_override = self.spec["character_cards"].get(current_agent)
                profile = resolve_agent_profile(current_agent, custom_override=char_override)
                if profile and profile.persona:
                    identity_section = profile.persona.render_prompt_section(agent_id=profile.id, role=role_name)
                    parts.append(identity_section)
            except Exception as e:
                self.logger.warning("Failed rendering persona section for %s: %s", current_agent, e)

        # 2. Active A2A Turn Section (if scheduled during an active conversational turn)
        if active_a2a_turn and isinstance(active_a2a_turn, dict):
            conv_id = active_a2a_turn.get("conversationId") or "conv_default"
            msg_id = active_a2a_turn.get("incomingMessageId") or "msg_unknown"
            sender = active_a2a_turn.get("from", {})
            sender_name = sender.get("displayName") or sender.get("id") if isinstance(sender, dict) else str(sender)
            intent = active_a2a_turn.get("intent") or "review_request"
            corr_id = active_a2a_turn.get("correlationId") or f"corr_{msg_id}"
            turn_text = active_a2a_turn.get("text") or ""

            example_block = json.dumps({
                "intent": "correction_result" if intent == "correction_request" else "review_result",
                "to": [sender.get("id") if isinstance(sender, dict) and sender.get("id") else str(sender_name).lower()],
                "text": "Provide your technical assessment or explanation here.",
                "conversationId": conv_id,
                "replyTo": msg_id,
                "correlationId": corr_id,
            }, indent=2)

            a2a_section = [
                "--- LYSSTACK ACTIVE A2A TURN ---",
                f"conversationId: {conv_id}",
                f"incomingMessageId: {msg_id}",
                f"replyExpectedFrom: {current_agent}",
                "",
                f"[from: {sender_name}]",
                f"intent: {intent}",
                "",
                turn_text,
                "",
                "When replying to another agent, emit a machine-readable response in this structured format:",
                LYSSTACK_A2A_START,
                example_block,
                LYSSTACK_A2A_END,
                "--- END ACTIVE A2A TURN ---",
            ]
            parts.append("\n".join(a2a_section))

        # 3. Base phase prompt / Job instructions
        parts.append(base_prompt)

        # 4. Context bundle (if configured)
        if self.context_bundle:
            parts.append(self.context_bundle)

        # 5. Operational thread history (handoffs, test results)
        thread_section = self.build_operational_thread_section(current_agent)
        if thread_section:
            parts.append(thread_section)

        # 6. Mailbox / A2A messages
        if current_agent:
            if mailbox_messages is None:
                mailbox_messages = self.fetch_pending_mailbox_messages(current_agent)
            mb_section = self.build_mailbox_messages_section(current_agent, mailbox_messages)
            if mb_section:
                parts.append(mb_section)

        return "\n\n".join(parts)

    def _load_verification_spec(self):
        verification = self.spec.get("verification", [])
        if not isinstance(verification, list):
            self._invalid_verification("'verification' must be a JSON array")

        names = set()
        normalized = []
        integration_dir = self.worktree_root / "integration"
        for index, raw_step in enumerate(verification, start=1):
            if not isinstance(raw_step, dict):
                self._invalid_verification(
                    f"verification step {index} must be a JSON object"
                )

            name = raw_step.get("name")
            if not isinstance(name, str) or not name.strip():
                self._invalid_verification(
                    f"verification step {index} requires a non-empty name"
                )
            if name in names:
                self._invalid_verification(
                    f"duplicate verification step name: {name}"
                )
            names.add(name)

            command = raw_step.get("command")
            if (
                not isinstance(command, list)
                or not command
                or any(not isinstance(argument, str) for argument in command)
            ):
                self._invalid_verification(
                    f"verification step '{name}' command must be a non-empty array of strings"
                )

            cwd = raw_step.get("cwd", ".")
            if not isinstance(cwd, str) or not cwd.strip():
                self._invalid_verification(
                    f"verification step '{name}' cwd must be a non-empty relative path"
                )
            if Path(cwd).is_absolute() or PureWindowsPath(cwd).anchor:
                self._invalid_verification(
                    f"verification step '{name}' cwd must be relative to the integration worktree"
                )

            timeout = raw_step.get(
                "timeout_seconds",
                self.limits.get("timeout_seconds", 300),
            )
            if (
                isinstance(timeout, bool)
                or not isinstance(timeout, (int, float))
                or timeout <= 0
            ):
                self._invalid_verification(
                    f"verification step '{name}' timeout_seconds must be positive"
                )

            step = {
                "name": name,
                "command": list(command),
                "cwd": cwd,
                "timeout_seconds": timeout,
            }
            self._resolve_verification_cwd(step, integration_dir)
            normalized.append(step)
        return normalized

    def _validate_phase_roles(self):
        for phase in self.spec.get("phases", []):
            self.resolve_phase_role(phase)

    def _validate_phase_permissions(self):
        for index, phase in enumerate(self.spec.get("phases", []), start=1):
            if "permissions" not in phase:
                continue
            permissions = phase["permissions"]
            if not isinstance(permissions, dict):
                self._invalid_phase_permissions(
                    index, "permissions must be an object"
                )
            commands = permissions.get("commands", [])
            if not isinstance(commands, list) or any(
                not isinstance(command, str) or not command.strip()
                for command in commands
            ):
                self._invalid_phase_permissions(
                    index,
                    "permissions.commands must be an array of non-empty strings",
                )

    @staticmethod
    def _invalid_phase_permissions(index, message):
        raise SprintRunnerError(
            "FAILED_INVALID_PHASE_PERMISSIONS",
            f"Phase {index} {message}",
        )

    def resolve_phase_role(self, phase):
        if "role" not in phase:
            return "legacy"
        role = phase["role"]
        if not isinstance(role, str) or role not in self.PHASE_ROLES:
            raise SprintRunnerError(
                "FAILED_UNKNOWN_ROLE",
                f"Unknown phase role: {role}",
            )
        return role

    def validate_execution_plan(self):
        """Validate phase inputs needed before any agent can run."""
        for phase in self.spec.get("phases", []):
            self.resolve_phase_role(phase)
            self.agent_registry.get(phase.get("agent"))
            self._get_backend(self.resolve_backend_name(phase))
            prompt_value = phase.get("prompt_file")
            if not isinstance(prompt_value, str) or not prompt_value.strip():
                raise SprintRunnerError(
                    "FAILED_MISSING_PROMPT",
                    "Phase prompt_file must be a non-empty path string",
                )
            prompt_file = self.resolve_prompt_file(phase)
            if not prompt_file.is_file():
                raise SprintRunnerError(
                    "FAILED_MISSING_PROMPT",
                    f"Prompt file not found: {prompt_file}",
                )

    def validate_preflight_worktree_config(self):
        """Validate refs and worktree layout without changing repository state."""
        base_ref = self.spec.get("base_ref") or self.spec.get("base_branch", "main")
        target_branch = self.spec.get("target_branch", "s02/integration")
        base_result = self.run_cmd(
            ["git", "rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}"],
            cwd=self.target_repo,
            check=False,
        )
        if base_result.returncode != 0:
            raise SprintRunnerError(
                "FAILED_INVALID_WORKTREE",
                f"Configured base ref does not resolve to a commit: {base_ref}",
            )

        branches = [("target_branch", target_branch)]
        worktree_paths = {self.worktree_root / "integration"}
        for index, phase in enumerate(self.spec.get("phases", []), start=1):
            branch = phase.get("branch")
            branches.append((f"phase {index} branch", branch))
            worktree_value = phase.get("worktree_dir")
            if (
                not isinstance(worktree_value, str)
                or not worktree_value.strip()
                or Path(worktree_value).is_absolute()
                or PureWindowsPath(worktree_value).anchor
                or ".." in PureWindowsPath(worktree_value).parts
            ):
                raise SprintRunnerError(
                    "FAILED_INVALID_WORKTREE",
                    f"Phase {index} worktree_dir must be a contained relative path",
                )
            worktree_path = (self.worktree_root / worktree_value).resolve()
            try:
                worktree_path.relative_to(self.worktree_root.resolve())
            except ValueError as error:
                raise SprintRunnerError(
                    "FAILED_INVALID_WORKTREE",
                    f"Phase {index} worktree_dir escapes worktree_root",
                ) from error
            if worktree_path in worktree_paths:
                raise SprintRunnerError(
                    "FAILED_INVALID_WORKTREE",
                    f"Duplicate worktree path configured for phase {index}: {worktree_value}",
                )
            worktree_paths.add(worktree_path)

        seen_branches = set()
        for label, branch in branches:
            if not isinstance(branch, str) or not branch.strip():
                raise SprintRunnerError(
                    "FAILED_INVALID_WORKTREE",
                    f"{label} must be a non-empty Git branch name",
                )
            branch_result = self.run_cmd(
                ["git", "check-ref-format", "--branch", branch],
                cwd=self.target_repo,
                check=False,
            )
            if branch_result.returncode != 0 or branch in seen_branches:
                raise SprintRunnerError(
                    "FAILED_INVALID_WORKTREE",
                    f"Invalid or duplicate {label}: {branch}",
                )
            seen_branches.add(branch)

    @staticmethod
    def _invalid_verification(message):
        raise SprintRunnerError("FAILED_INVALID_VERIFICATION_SPEC", message)

    def _resolve_verification_cwd(self, step, integration_dir):
        integration_dir = integration_dir.resolve()
        candidate = (integration_dir / step["cwd"]).resolve()
        try:
            candidate.relative_to(integration_dir)
        except ValueError:
            self._invalid_verification(
                f"verification step '{step['name']}' cwd escapes the integration worktree"
            )
        return candidate

    def _setup_logging(self):
        self.run_dir.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger(f"HermesSprintRunner.{id(self)}")
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        logger.propagate = False
        
        file_handler = logging.FileHandler(self.log_file)
        console_handler = logging.StreamHandler(sys.stdout)
        
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        return logger

    def run_cmd(self, cmd, cwd=None, timeout=None, check=True):
        cwd = cwd or self.target_repo
        timeout = timeout or self.limits.get("timeout_seconds", 300)
        self.logger.debug(f"Executing command: {' '.join(cmd) if isinstance(cmd, list) else cmd} (cwd: {cwd})")
        
        if self.dry_run and any(k in cmd for k in ["commit", "merge", "push", "add", "reset"]):
            self.logger.info(f"[DRY-RUN] Would run: {cmd}")
            return subprocess.CompletedProcess(cmd, 0, stdout="[dry-run]", stderr="")

        try:
            res = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if check and res.returncode != 0:
                if "Permission denied" in res.stderr or "permission denied" in res.stderr:
                    raise SprintRunnerError("FAILED_PERMISSION_DENIED", f"Permission denied during command: {cmd}\n{res.stderr}")
                raise SprintRunnerError("FAILED_COMMAND_EXECUTION", f"Command failed: {cmd}\nExit Code: {res.returncode}\nStderr: {res.stderr}")
            return res
        except subprocess.TimeoutExpired:
            raise SprintRunnerError("FAILED_TIMEOUT", f"Command timed out after {timeout} seconds: {cmd}")

    def prepare_environment(self):
        self.logger.info("=== Preparing Sprint Worktree Environment ===")
        if not self.target_repo.exists():
            raise SprintRunnerError(
                "FAILED_TARGET_REPO_MISSING",
                f"Target repo does not exist at {self.target_repo}",
            )
        if not self.target_repo.is_dir():
            raise SprintRunnerError(
                "FAILED_TARGET_REPO_NOT_GIT",
                f"Target repo is not a Git working tree: {self.target_repo}",
            )

        repository_check = self.run_cmd(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=self.target_repo,
            check=False,
        )
        if (
            repository_check.returncode != 0
            or repository_check.stdout.strip() != "true"
        ):
            raise SprintRunnerError(
                "FAILED_TARGET_REPO_NOT_GIT",
                f"Target repo is not a Git working tree: {self.target_repo}",
            )

        # Target repository safety: MUST fail if dirty.
        res = self.run_cmd(["git", "status", "--porcelain"], cwd=self.target_repo)
        if res.stdout.strip():
            raise SprintRunnerError(
                "FAILED_DIRTY_REPO",
                f"Target repo at {self.target_repo} has uncommitted changes:\n{res.stdout.strip()}"
            )

        self.worktree_root.mkdir(parents=True, exist_ok=True)
        base_ref = self.spec.get("base_ref") or self.spec.get("base_branch", "main")
        target_branch = self.spec.get("target_branch", "s02/integration")

        # 1. Setup integration worktree
        integration_dir = self.worktree_root / "integration"
        self._ensure_worktree(integration_dir, target_branch, base_ref)

        # 2. Setup agent worktrees
        for phase in self.spec.get("phases", []):
            self.agent_registry.get(phase["agent"])
            self._get_backend(self.resolve_backend_name(phase))
            wt_dir = self.worktree_root / phase["worktree_dir"]
            branch = phase["branch"]
            self._ensure_worktree(wt_dir, branch, target_branch)

    def _ensure_worktree(self, path, branch, base_branch):
        if path.exists():
            self.logger.info(f"Validating existing worktree at {path} (expected branch: {branch})")
            # 1. Check if inside worktree
            res_wt = self.run_cmd(["git", "rev-parse", "--is-inside-work-tree"], cwd=path, check=False)
            if res_wt.returncode != 0 or res_wt.stdout.strip() != "true":
                raise SprintRunnerError("FAILED_INVALID_WORKTREE", f"Directory {path} exists but is not a valid Git worktree.")
            
            # 2. Check current branch
            res_branch = self.run_cmd(["git", "branch", "--show-current"], cwd=path, check=False)
            curr_branch = res_branch.stdout.strip()
            if curr_branch != branch:
                raise SprintRunnerError("FAILED_WRONG_BRANCH", f"Worktree at {path} is on branch '{curr_branch}', expected '{branch}'.")

            # 3. Check clean status
            res_status = self.run_cmd(["git", "status", "--porcelain"], cwd=path, check=False)
            if res_status.stdout.strip():
                raise SprintRunnerError("FAILED_DIRTY_WORKTREE", f"Worktree at {path} has uncommitted changes:\n{res_status.stdout.strip()}")
        else:
            self.logger.info(f"Creating worktree at {path} for branch {branch} (from {base_branch})")
            res = self.run_cmd(["git", "branch", "--list", branch], cwd=self.target_repo)
            if res.stdout.strip():
                self.run_cmd(["git", "worktree", "add", str(path), branch], cwd=self.target_repo)
            else:
                self.run_cmd(["git", "worktree", "add", "-b", branch, str(path), base_branch], cwd=self.target_repo)

        # Clean, correctly assigned sprint branches are controller-owned and may
        # contain commits from an earlier run. Resetting them makes reruns start
        # from the configured state while dirty worktrees still fail above.
        self.logger.info(
            "Resetting worktree %s (%s) to configured start %s",
            path.name,
            branch,
            base_branch,
        )
        self.run_cmd(["git", "reset", "--hard", base_branch], cwd=path)

    def sync_phase_worktree(self, worktree, target_branch):
        self.logger.info(
            "Synchronizing phase worktree (%s) to latest %s",
            worktree.name,
            target_branch,
        )
        self.run_cmd(["git", "fetch", ".", target_branch], cwd=worktree)
        self.run_cmd(["git", "reset", "--hard", target_branch], cwd=worktree)

    # Compatibility helpers retained for callers that validated output through the runner.
    def parse_antigravity_stream_json(self, stdout_text, stderr_text=""):
        from agents.antigravity import AntigravityAdapter

        return AntigravityAdapter.parse_stream_json(stdout_text, stderr_text)

    def parse_claude_json(self, stdout_text, stderr_text=""):
        from agents.claude import ClaudeAdapter

        return ClaudeAdapter.parse_json(stdout_text, stderr_text)

    def resolve_backend_name(self, phase):
        return (
            phase.get("execution_backend")
            or self.backend_override
            or self.spec.get("execution_backend")
            or "subprocess"
        )

    def _get_backend(self, backend_name):
        if backend_name not in self._backend_cache:
            self._backend_cache[backend_name] = self.backend_registry.get(
                backend_name,
                run_dir=self.run_dir,
                sprint_id=self.sprint_id,
                logger=self.logger,
                keep_workspace=self.spec.get("keep_herdr_workspace", True),
            )
        return self._backend_cache[backend_name]

    def execute_agent(self, phase, wt_dir, mailbox_messages=None, active_a2a_turn=None):
        agent_name = phase["agent"]
        sub_profile = (
            getattr(self, "subagent_manager", None).get_subagent(agent_name)
            if getattr(self, "subagent_manager", None)
            else None
        )
        parent_provider = (
            sub_profile.provider
            or sub_profile.parentAgentId
            if sub_profile
            else phase.get("provider") or phase.get("parent_agent")
        )
        try:
            adapter = self.agent_registry.get(agent_name)
        except SprintRunnerError:
            if parent_provider:
                adapter = self.agent_registry.get(parent_provider)
            else:
                raise
        backend = self._get_backend(self.resolve_backend_name(phase))
        prompt_file = self.resolve_prompt_file(phase)
        context = AgentContext(
            runner=self,
            phase=phase,
            worktree=wt_dir,
            prompt=self.build_effective_prompt(
                prompt_file.read_text(encoding="utf-8").strip(),
                current_agent=agent_name,
                mailbox_messages=mailbox_messages,
                role=phase.get("role"),
                active_a2a_turn=active_a2a_turn,
            ),
            options=phase.get("cmd_options", {}),
            stdout_file=self.run_dir / f"{phase['name']}_{agent_name}_stdout.log",
            stderr_file=self.run_dir / f"{phase['name']}_{agent_name}_stderr.log",
            timeout_seconds=self.limits.get("timeout_seconds", 300),
            backend=backend,
        )
        raw_res = adapter.execute(context)

        # Parse structured A2A output from execution result stdout
        if parse_a2a_output:
            return parse_a2a_output(
                raw_text=getattr(raw_res, "stdout", "") or "",
                execution_result=raw_res,
                publisher=default_publisher,
                job_id=self.job_id,
                agent_id=agent_name,
            )
        return raw_res

    def inspect_changed_files(self, worktree_path):
        """Return target source changes without imposing role semantics."""
        res = self.run_cmd(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=worktree_path,
        )
        lines = [line for line in res.stdout.strip().split("\n") if line.strip()]
        self.logger.info("Changed target files count in %s: %s", worktree_path.name, len(lines))
        return lines

    def validate_changed_files(self, worktree_path):
        """Legacy required-change validation retained for compatibility callers."""
        lines = self.inspect_changed_files(worktree_path)
        max_limit = self.limits.get("max_changed_files", 15)
        if len(lines) == 0:
            raise SprintRunnerError(
                "FAILED_NO_CHANGES",
                f"Worktree {worktree_path.name} produced NO file changes."
            )
        if len(lines) > max_limit:
            raise SprintRunnerError(
                "FAILED_EXCESSIVE_FILES",
                f"Worktree {worktree_path.name} changed {len(lines)} files, exceeding limit of {max_limit}."
            )
        return lines

    def validate_handoff_file(self, worktree_path, expected_handoff):
        worktree_path = worktree_path.resolve()
        handoff_path = (worktree_path / expected_handoff).resolve()
        try:
            handoff_path.relative_to(worktree_path)
        except ValueError as error:
            raise SprintRunnerError(
                "FAILED_INVALID_HANDOFF",
                f"Handoff path escapes worktree: {expected_handoff}",
            ) from error
        self.logger.info(f"Checking expected handoff file: {handoff_path}")
        if not handoff_path.is_file() or handoff_path.stat().st_size == 0:
            raise SprintRunnerError(
                "FAILED_MISSING_HANDOFF",
                f"Required handoff file '{expected_handoff}' is missing or empty in {worktree_path}."
            )
        return handoff_path

    @staticmethod
    def _safe_filename_component(value):
        return "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in value
        ) or "unknown"

    def capture_handoff(
        self,
        phase_index,
        role,
        agent,
        worktree_path,
        expected_handoff,
    ):
        handoff_path = self.validate_handoff_file(worktree_path, expected_handoff)
        destination = self.run_dir / "handoffs" / (
            f"{phase_index:02d}_{self._safe_filename_component(role)}_"
            f"{self._safe_filename_component(agent)}.md"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            handoff_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        return handoff_path

    def _prepare_handoff_path(self, worktree_path, expected_handoff):
        worktree_path = worktree_path.resolve()
        handoff_path = (worktree_path / expected_handoff).resolve()
        try:
            handoff_path.relative_to(worktree_path)
        except ValueError as error:
            raise SprintRunnerError(
                "FAILED_INVALID_HANDOFF",
                f"Handoff path escapes worktree: {expected_handoff}",
            ) from error
        original_content = handoff_path.read_bytes() if handoff_path.is_file() else None
        if handoff_path.exists() and not handoff_path.is_file():
            raise SprintRunnerError(
                "FAILED_INVALID_HANDOFF",
                f"Handoff path is not a file: {expected_handoff}",
            )
        if handoff_path.is_file():
            handoff_path.unlink()
        return handoff_path, original_content

    @staticmethod
    def _restore_handoff_path(handoff_path, original_content):
        if original_content is None:
            if handoff_path.exists():
                handoff_path.unlink()
            return
        handoff_path.parent.mkdir(parents=True, exist_ok=True)
        handoff_path.write_bytes(original_content)

    def validate_python_syntax(self, worktree_path):
        self.logger.info(f"Validating Python syntax in {worktree_path}")
        py_files = list(worktree_path.rglob("*.py"))
        for py_file in py_files:
            try:
                py_compile.compile(str(py_file), doraise=True)
            except py_compile.PyCompileError as e:
                raise SprintRunnerError(
                    "FAILED_SYNTAX_ERROR",
                    f"Python syntax error in {py_file.name}: {e}"
                )

    def execute_phase(self, phase, phase_index=1):
        phase_name = phase["name"]
        agent = phase["agent"]
        role = self.resolve_phase_role(phase)
        wt_dir = self.worktree_root / phase["worktree_dir"]
        prompt_file = self.resolve_prompt_file(phase)
        expected_handoff = phase["expected_handoff"]
        commit_msg = phase["commit_message"]

        self.logger.info(f"\n=== Executing Phase: {phase_name} (Agent: {agent}) ===")
        backend_name = self.resolve_backend_name(phase)
        self._get_backend(backend_name)

        if default_publisher:
            default_publisher.publish(
                source_id=agent,
                source_kind="agent",
                kind="phase.started",
                detail=f"Starting phase {phase_name} ({role}) with agent {agent}",
                job_id=self.job_id,
                metadata={
                    "phase": phase_name,
                    "role": role,
                    "agent": agent,
                    "order": phase_index,
                },
            )

        try:
            if not prompt_file.exists():
                raise SprintRunnerError("FAILED_MISSING_PROMPT", f"Prompt file not found: {prompt_file}")

            # Every phase after the first starts from the latest integration state.
            if self.run_summary["phases"]:
                target_branch = self.spec.get("target_branch", "s02/integration")
                self.sync_phase_worktree(wt_dir, target_branch)

            # Fetch pending mailbox messages specifically targeted to this agent for this job
            pending_mailbox_messages = self.fetch_pending_mailbox_messages(agent)
            consumed_ids = [m["id"] for m in pending_mailbox_messages if "id" in m]

            handoff_path, original_handoff = self._prepare_handoff_path(
                wt_dir,
                expected_handoff,
            )
            try:
                if not self.skip_agent_exec and not self.dry_run:
                    execution_result = self.execute_agent(phase, wt_dir, mailbox_messages=pending_mailbox_messages)
                else:
                    execution_result = None
                    self.logger.info(f"Skipping agent execution CLI (skip_agent_exec={self.skip_agent_exec}, dry_run={self.dry_run})")

                self.capture_handoff(
                    phase_index,
                    role,
                    agent,
                    wt_dir,
                    expected_handoff,
                )

                # Successfully executed agent -> acknowledge consumed mailbox messages
                for msg_id in consumed_ids:
                    if default_publisher and default_publisher.enabled:
                        default_publisher.acknowledge_message(agent, msg_id)
                    self._consumed_message_ids.add(msg_id)
                if consumed_ids:
                    self.logger.info("Acknowledged %s mailbox message(s) for agent %s", len(consumed_ids), agent)
            finally:
                self._restore_handoff_path(handoff_path, original_handoff)

            changed_files = self.inspect_changed_files(wt_dir)
            max_limit = self.limits.get("max_changed_files", 15)
            if role == "verifier" and changed_files:
                raise SprintRunnerError(
                    "FAILED_FORBIDDEN_CHANGES",
                    f"Verifier phase '{phase_name}' modified {len(changed_files)} target files.",
                )
            if role != "verifier" and len(changed_files) > max_limit:
                raise SprintRunnerError(
                    "FAILED_EXCESSIVE_FILES",
                    f"Worktree {wt_dir.name} changed {len(changed_files)} files, exceeding limit of {max_limit}.",
                )
            if role in {"builder", "legacy"} and not changed_files:
                raise SprintRunnerError(
                    "FAILED_NO_CHANGES",
                    f"Worktree {wt_dir.name} produced NO file changes.",
                )

            self.validate_python_syntax(wt_dir)

            should_integrate = bool(changed_files) and role != "verifier"
            commit_sha = None
            if should_integrate:
                self.logger.info(f"Controller staging changes in {wt_dir.name}")
                self.run_cmd(["git", "add", "."], cwd=wt_dir)
                self.run_cmd(["git", "commit", "-m", commit_msg], cwd=wt_dir)

                sha_res = self.run_cmd(["git", "rev-parse", "HEAD"], cwd=wt_dir)
                commit_sha = sha_res.stdout.strip()
                self.logger.info(f"Committed phase changes: {commit_sha[:7]} - {commit_msg}")

                integration_dir = self.worktree_root / "integration"
                self.logger.info(f"Controller merging commit {commit_sha[:7]} into integration worktree")
                self.run_cmd(["git", "merge", "--no-ff", "-m", f"merge({self.sprint_id}): merge {agent} phase ({commit_sha[:7]})", commit_sha], cwd=integration_dir)

            phase_result = {
                "phase": phase_name,
                "role": role,
                "agent": agent,
                "backend": backend_name,
                "status": "SUCCESS",
                "commit_sha": commit_sha,
                "changed_files_count": len(changed_files),
                "integrated": should_integrate,
                "handoff": "captured",
                "runtime_metadata": (
                    dict(execution_result.runtime_metadata) if execution_result else {}
                ),
            }
            self.run_summary["phases"].append(phase_result)

            # Phase 5 Operational Messaging & Artifact Registration
            phases_list = self.spec.get("phases", [])
            next_agent = phases_list[phase_index]["agent"] if phase_index < len(phases_list) else "hermes_runner"
            intent = (
                "review_request" if role == "builder" else (
                    "verification_request" if role == "hardener" else (
                        "verification_result" if role == "verifier" else "handoff"
                    )
                )
            )

            msg_artifacts = []
            if commit_sha:
                art_commit = {
                    "id": f"art_commit_{phase_index}",
                    "type": "git_commit",
                    "label": f"{phase_name} commit ({commit_sha[:7]})",
                    "ref": commit_sha,
                    "jobId": self.job_id,
                    "phaseId": f"phase-{phase_index}-{phase_name}",
                }
                self._record_artifact(art_commit)
                msg_artifacts.append(art_commit)

            handoff_rel = f"handoffs/{phase_index:02d}_{self._safe_filename_component(role)}_{self._safe_filename_component(agent)}.md"
            art_handoff = {
                "id": f"art_handoff_{phase_index}",
                "type": "handoff",
                "label": f"{phase_name} handoff ({expected_handoff})",
                "ref": handoff_rel,
                "jobId": self.job_id,
                "phaseId": f"phase-{phase_index}-{phase_name}",
            }
            self._record_artifact(art_handoff)
            msg_artifacts.append(art_handoff)

            if role == "builder":
                msg_text = f"{phase_name} ({role}) implementation completed. Commit {commit_sha[:7] if commit_sha else 'n/a'}. {len(changed_files)} files modified. Please review."
            elif role == "hardener":
                msg_text = f"{phase_name} ({role}) review and hardening completed. Commit {commit_sha[:7] if commit_sha else 'n/a'}. Ready for verification."
            elif role == "verifier":
                msg_text = f"{phase_name} ({role}) verification completed."
            else:
                msg_text = f"{phase_name} completed successfully."

            from_actor = {"id": agent, "kind": "agent", "displayName": agent.capitalize()}
            to_actor = {
                "id": next_agent,
                "kind": "agent" if any(p.get("agent") == next_agent for p in phases_list) else "runtime",
                "displayName": next_agent.capitalize(),
            }

            conv_id = f"conv_phase_{phase_index}_{phase_name}"
            self._record_message(
                from_actor=from_actor,
                to_actors=[to_actor],
                kind="handoff" if role != "verifier" else "verification_result",
                text=msg_text,
                intent=intent,
                conversation_id=conv_id,
                phase_id=f"phase-{phase_index}-{phase_name}",
                artifact_refs=msg_artifacts,
            )

            # Hermes A2A Multi-Agent Turn Scheduling (Phase 6)
            self.schedule_a2a_turns(phase, wt_dir, conversation_id=conv_id)

            if default_publisher:
                default_publisher.publish(
                    source_id=agent,
                    source_kind="agent",
                    kind="phase.completed",
                    detail=f"Phase {phase_name} completed successfully",
                    job_id=self.job_id,
                    metadata={
                        "phase": phase_name,
                        "role": role,
                        "agent": agent,
                        "commitSha": commit_sha,
                        "changedFilesCount": len(changed_files),
                    },
                )
        except Exception as exc:
            err_msg = getattr(exc, "message", str(exc))
            self._record_message(
                from_actor={"id": agent, "kind": "agent", "displayName": agent.capitalize()},
                to_actors=[
                    {"id": "hermes_runner", "kind": "runtime", "displayName": "Hermes Runner"},
                    {"id": "lysstack", "kind": "runtime", "displayName": "LysStack"},
                ],
                kind="warning",
                intent="phase_failure",
                text=f"Phase {phase_name} ({agent}) failed: {err_msg}",
                phase_id=f"phase-{phase_index}-{phase_name}",
            )
            if default_publisher:
                default_publisher.publish(
                    source_id=agent,
                    source_kind="agent",
                    kind="phase.failed",
                    detail=f"Phase {phase_name} failed: {err_msg}",
                    job_id=self.job_id,
                    metadata={
                        "phase": phase_name,
                        "role": role,
                        "agent": agent,
                        "error": err_msg,
                    },
                )
            raise

    def schedule_a2a_turns(self, phase, wt_dir, conversation_id=None):
        """
        Hermes A2A Turn Scheduler (Phase 6 / Phase 6.1):
        Discovers pending schedulable messages from remote control plane inboxes and local store.
        Executes bounded multi-agent turns with structured prompt injection, extracts structured output,
        records outgoing messages with authoritative context inheritance, and tracks turn ACKs.
        Guarantees that agents never call each other directly; Hermes remains the sole execution authority.
        """
        a2a_config = self.limits.get("a2a", {}) if isinstance(self.limits.get("a2a"), dict) else {}
        if not a2a_config.get("enabled", True):
            return

        max_phase_turns = a2a_config.get("max_turns_per_phase", 4)
        max_job_turns = a2a_config.get("max_turns_per_job", 12)
        phase_turns = 0
        limit_reached = False

        phases_by_agent = {p.get("agent"): p for p in self.spec.get("phases", [])}

        while True:
            # Check turn limits
            if self.job_a2a_turns >= max_job_turns or phase_turns >= max_phase_turns:
                self.logger.warning(
                    "A2A conversation turn limit reached (job: %s/%s, phase: %s/%s). Halting A2A turns.",
                    self.job_a2a_turns, max_job_turns, phase_turns, max_phase_turns,
                )
                limit_reached = True
                if default_publisher:
                    default_publisher.publish(
                        source_id="hermes_runner",
                        source_kind="runtime",
                        kind="conversation.limit_reached",
                        detail=f"A2A conversation turn limit reached ({self.job_a2a_turns} turns)",
                        job_id=self.job_id,
                        metadata={
                            "conversationId": conversation_id,
                            "jobTurns": self.job_a2a_turns,
                            "maxJobTurns": max_job_turns,
                            "phaseTurns": phase_turns,
                            "maxPhaseTurns": max_phase_turns,
                        },
                    )
                break

            consumed = getattr(self, "_consumed_message_ids", set())
            candidate_messages = []
            seen_ids = set()

            # 1. Discover pending messages from Remote Control Plane inboxes (LysStack) with thread/job scoping
            if default_publisher and default_publisher.enabled:
                for ag_id in phases_by_agent:
                    try:
                        remote_entries = default_publisher.fetch_agent_inbox(
                            agent_id=ag_id,
                            state="DELIVERED",
                            job_id=self.job_id,
                            thread_id=self.thread_id,
                            conversation_id=conversation_id,
                        )
                        for entry in remote_entries:
                            r_msg = entry.get("message")
                            if isinstance(r_msg, dict):
                                mid = r_msg.get("id")
                                if mid and mid not in consumed and mid not in seen_ids:
                                    candidate_messages.append(r_msg)
                                    seen_ids.add(mid)
                    except Exception as exc:
                        self.logger.debug("Failed querying remote inbox for %s: %s", ag_id, exc)

            # 2. Discover pending messages from Local Messages store
            for l_msg in self.local_messages:
                mid = l_msg.get("id")
                if mid and mid not in consumed and mid not in seen_ids:
                    candidate_messages.append(l_msg)
                    seen_ids.add(mid)

            # 3. Filter candidate messages for the active thread, job, and conversation
            pending_a2a = []
            for msg in candidate_messages:
                # Must match thread
                if msg.get("threadId") and msg.get("threadId") != self.thread_id:
                    continue
                # Must match job
                if msg.get("jobId") and msg.get("jobId") not in (self.job_id, getattr(self, "sprint_id", None)):
                    continue
                # If conversation_id is specified, filter by it
                if conversation_id and msg.get("conversationId") != conversation_id:
                    continue

                kind = msg.get("kind")
                intent = msg.get("intent")
                # Handoffs are phase-transition boundaries for the normal phase loop, not inline A2A turns
                if kind == "handoff":
                    continue

                # Schedulable: A2A conversational messages or request intents, or tool_result continuations
                is_schedulable = (
                    (kind in ("a2a", "tool_result", "delegation") or intent in SCHEDULABLE_INTENTS or intent == "tool_result")
                    and (intent not in TERMINAL_INTENTS or kind == "tool_result" or intent == "tool_result")
                )

                if is_schedulable:
                    to_actors = msg.get("to", [])
                    if to_actors:
                        to_id = to_actors[0].get("id") if isinstance(to_actors[0], dict) else str(to_actors[0])
                        if to_id in phases_by_agent:
                            pending_a2a.append(msg)

            if not pending_a2a:
                break

            target_msg = pending_a2a[0]
            to_actors = target_msg.get("to", [])
            target_agent = to_actors[0].get("id") if isinstance(to_actors[0], dict) else str(to_actors[0])
            target_phase = phases_by_agent[target_agent]
            target_wt = self.worktree_root / target_phase.get("worktree_dir", "integration")

            self.job_a2a_turns += 1
            phase_turns += 1

            self.logger.info(
                "Hermes scheduling A2A turn #%s for %s in conversation %s (replying to %s)",
                self.job_a2a_turns, target_agent, conversation_id, target_msg.get("id"),
            )

            if default_publisher:
                default_publisher.publish(
                    source_id="hermes_runner",
                    source_kind="runtime",
                    kind="conversation.turn",
                    detail=f"Scheduling A2A turn #{self.job_a2a_turns} for {target_agent}",
                    job_id=self.job_id,
                    metadata={
                        "conversationId": conversation_id,
                        "turn": self.job_a2a_turns,
                        "targetAgent": target_agent,
                        "replyTo": target_msg.get("id"),
                        "intent": target_msg.get("intent"),
                    },
                )

            # Build active A2A turn context for prompt injection
            active_a2a_turn = {
                "conversationId": conversation_id or target_msg.get("conversationId"),
                "incomingMessageId": target_msg.get("id"),
                "from": target_msg.get("from"),
                "intent": target_msg.get("intent"),
                "text": target_msg.get("text"),
                "correlationId": target_msg.get("correlationId"),
            }

            # Fetch pending mailbox messages specifically for target agent
            target_mailbox = self.fetch_pending_mailbox_messages(target_agent)
            target_consumed_ids = [m["id"] for m in target_mailbox if "id" in m]
            if target_msg.get("id") and target_msg["id"] not in target_consumed_ids:
                target_consumed_ids.append(target_msg["id"])

            # Execute target agent with active A2A turn context using inspect.signature (no TypeError double-run)
            turn_result = None
            if not self.skip_agent_exec and not self.dry_run:
                try:
                    import inspect
                    sig = inspect.signature(self.execute_agent)
                    if "active_a2a_turn" in sig.parameters:
                        turn_result = self.execute_agent(
                            target_phase,
                            target_wt,
                            mailbox_messages=target_mailbox,
                            active_a2a_turn=active_a2a_turn,
                        )
                    else:
                        turn_result = self.execute_agent(
                            target_phase,
                            target_wt,
                            mailbox_messages=target_mailbox,
                        )
                except Exception as e:
                    self.logger.warning("Error during A2A turn execution for %s: %s", target_agent, e)
                    # Do not acknowledge on execution failure to allow retry
                    break

            # Task completion check: if target_msg or an outgoing message reported task_result
            incoming_meta = target_msg.get("metadata") or {}
            task_id = incoming_meta.get("taskId")
            if target_msg.get("intent") == "task_result" and task_id:
                if task_id in self.task_assignments:
                    self.task_assignments[task_id].status = "completed"
                    self.task_assignments[task_id].completedAt = datetime.now().isoformat()
                    if default_publisher:
                        default_publisher.publish(
                            source_id="hermes_runner",
                            source_kind="runtime",
                            kind="delegation.completed",
                            detail=f"Task {task_id} completed by {target_agent}.",
                            job_id=self.job_id,
                            metadata={"taskId": task_id, "completedBy": target_agent},
                        )

            # Process and record outgoing structured A2A messages if present
            outgoing_msgs = getattr(turn_result, "outgoing_messages", []) or []
            for out_msg in outgoing_msgs:
                out_conv_id = conversation_id or target_msg.get("conversationId") or out_msg.conversationId
                out_reply_to = out_msg.replyTo or target_msg.get("id")
                out_corr_id = out_msg.correlationId or target_msg.get("correlationId")

                if out_msg.intent == "task_result" and task_id:
                    if task_id in self.task_assignments:
                        self.task_assignments[task_id].status = "completed"
                        self.task_assignments[task_id].completedAt = datetime.now().isoformat()
                        if default_publisher:
                            default_publisher.publish(
                                source_id="hermes_runner",
                                source_kind="runtime",
                                kind="delegation.completed",
                                detail=f"Task {task_id} completed by {target_agent}.",
                                job_id=self.job_id,
                                metadata={"taskId": task_id, "completedBy": target_agent},
                            )

                # Validate replyTo graph consistency (reject invalid replyTo messages from scheduling)
                if validate_reply_to:
                    is_valid_reply = validate_reply_to(
                        reply_to=out_reply_to,
                        thread_id=self.thread_id,
                        conversation_id=out_conv_id,
                        known_messages=self.local_messages,
                        publisher=default_publisher,
                        job_id=self.job_id,
                        agent_id=target_agent,
                    )
                    if not is_valid_reply:
                        self.logger.warning(
                            "Rejecting outgoing A2A message with invalid replyTo %s from %s",
                            out_reply_to,
                            target_agent,
                        )
                        continue

                self._record_message(
                    from_actor={"id": target_agent, "kind": "agent", "displayName": target_agent.capitalize()},
                    to_actors=[{"id": rec, "kind": "agent", "displayName": rec.capitalize()} for rec in out_msg.to],
                    kind="a2a",
                    intent=out_msg.intent,
                    text=out_msg.text,
                    conversation_id=out_conv_id,
                    reply_to=out_reply_to,
                    correlation_id=out_corr_id,
                    phase_id=f"phase-{target_phase.get('name')}",
                    artifact_refs=out_msg.artifactRefs,
                    metadata=out_msg.metadata,
                )

            # Process outgoing Delegation Requests (Phase 7)
            del_requests = getattr(turn_result, "delegation_requests", []) or []
            max_delegations = self.limits.get("delegation", {}).get("max_delegations_per_job", 10) if isinstance(self.limits.get("delegation"), dict) else 10

            for del_req in del_requests:
                if self.job_delegations >= max_delegations:
                    self.logger.warning("Delegation limit reached (%s/%s). Skipping delegation.", self.job_delegations, max_delegations)
                    if default_publisher:
                        default_publisher.publish(
                            source_id="hermes_runner",
                            source_kind="runtime",
                            kind="delegation.limit_reached",
                            detail=f"Delegation limit reached ({self.job_delegations}/{max_delegations}).",
                            job_id=self.job_id,
                            metadata={"delegationId": del_req.id, "count": self.job_delegations},
                        )
                    continue

                # Set authoritative fields
                del_req.jobId = self.job_id
                del_req.threadId = self.thread_id
                del_req.conversationId = conversation_id or target_msg.get("conversationId") or self.thread_id
                del_req.parentMessageId = target_msg.get("id")
                del_req.requester = {"id": target_agent, "kind": "agent", "displayName": target_agent.capitalize()}

                if default_publisher:
                    default_publisher.publish(
                        source_id=target_agent,
                        source_kind="agent",
                        kind="delegation.requested",
                        detail=f"Agent {target_agent} requested delegation: {del_req.task[:100]}",
                        job_id=self.job_id,
                        metadata={"requestId": del_req.id, "requiredCapabilities": del_req.requiredCapabilities},
                    )

                decision = self.capability_registry.select_actor(
                    required_capabilities=del_req.requiredCapabilities,
                    preferred_actors=del_req.preferredActors,
                    excluded_actors=del_req.excludedActors,
                    available_actors=list(phases_by_agent.keys()),
                    request_id=del_req.id,
                    publisher=default_publisher,
                    job_id=self.job_id,
                )

                if decision.status == "selected" and decision.selectedActorId:
                    self.job_delegations += 1
                    selected_actor = decision.selectedActorId
                    task_id = f"task_{del_req.id}"
                    assignment = TaskAssignment(
                        taskId=task_id,
                        ownerActorId=selected_actor,
                        task=del_req.task,
                        status="queued",
                        delegatedBy=target_agent,
                        requiredCapabilities=del_req.requiredCapabilities,
                        jobId=self.job_id,
                        threadId=self.thread_id,
                        conversationId=del_req.conversationId,
                    )
                    self.task_assignments[task_id] = assignment

                    if default_publisher:
                        default_publisher.publish(
                            source_id="hermes_runner",
                            source_kind="runtime",
                            kind="delegation.selected",
                            detail=f"Delegated task {task_id} to actor {selected_actor}",
                            job_id=self.job_id,
                            metadata={
                                "taskId": task_id,
                                "selectedActorId": selected_actor,
                                "delegatedBy": target_agent,
                                "requiredCapabilities": del_req.requiredCapabilities,
                            },
                        )

                    self._record_message(
                        from_actor={"id": target_agent, "kind": "agent", "displayName": target_agent.capitalize()},
                        to_actors=[{"id": selected_actor, "kind": "agent", "displayName": selected_actor.capitalize()}],
                        kind="delegation",
                        intent="task_request",
                        text=del_req.task,
                        conversation_id=del_req.conversationId,
                        reply_to=target_msg.get("id"),
                        metadata={
                            "taskId": task_id,
                            "delegationRequestId": del_req.id,
                            "requiredCapabilities": del_req.requiredCapabilities,
                            "matchedCapabilities": decision.matchedCapabilities,
                            "delegatedBy": target_agent,
                        },
                    )
                else:
                    # Check if subagent creation is permitted
                    if del_req.allowSubagent and self.subagent_manager.allow_subagents:
                        parent_sub = self.subagent_manager.get_subagent(target_agent)
                        parent_depth = parent_sub.depth if parent_sub else 0
                        sub_profile = self.subagent_manager.create_subagent(
                            parent_agent_id=target_agent,
                            task=del_req.task,
                            capabilities=del_req.requiredCapabilities,
                            parent_depth=parent_depth,
                            publisher=default_publisher,
                            job_id=self.job_id,
                        )
                        if sub_profile:
                            self.capability_registry.register_actor(sub_profile)
                            phases_by_agent[sub_profile.id] = {
                                **target_phase,
                                "name": f"subagent_{sub_profile.id}",
                                "agent": sub_profile.id,
                                "parent_agent": target_agent,
                                "provider": sub_profile.provider,
                            }
                            self.job_delegations += 1
                            task_id = f"task_{del_req.id}"
                            assignment = TaskAssignment(
                                taskId=task_id,
                                ownerActorId=sub_profile.id,
                                task=del_req.task,
                                status="queued",
                                delegatedBy=target_agent,
                                requiredCapabilities=del_req.requiredCapabilities,
                                jobId=self.job_id,
                                threadId=self.thread_id,
                                conversationId=del_req.conversationId,
                            )
                            self.task_assignments[task_id] = assignment

                            self._record_message(
                                from_actor={"id": target_agent, "kind": "agent", "displayName": target_agent.capitalize()},
                                to_actors=[{"id": sub_profile.id, "kind": "agent", "displayName": sub_profile.displayName}],
                                kind="delegation",
                                intent="task_request",
                                text=del_req.task,
                                conversation_id=del_req.conversationId,
                                reply_to=target_msg.get("id"),
                                metadata={
                                    "taskId": task_id,
                                    "delegationRequestId": del_req.id,
                                    "requiredCapabilities": del_req.requiredCapabilities,
                                    "delegatedBy": target_agent,
                                    "subagent": True,
                                },
                            )
                        else:
                            if default_publisher:
                                default_publisher.publish(
                                    source_id="hermes_runner",
                                    source_kind="runtime",
                                    kind="delegation.rejected",
                                    detail=f"Subagent creation rejected for delegation {del_req.id}",
                                    job_id=self.job_id,
                                    metadata={"requestId": del_req.id, "reason": "subagent_creation_failed"},
                                )
                    else:
                        if default_publisher:
                            default_publisher.publish(
                                source_id="hermes_runner",
                                source_kind="runtime",
                                kind="delegation.rejected",
                                detail=f"No capable actor found for delegation: {del_req.task[:100]}",
                                job_id=self.job_id,
                                metadata={"requestId": del_req.id, "requiredCapabilities": del_req.requiredCapabilities},
                            )

            # Process outgoing Tool Invocations (Phase 7)
            tool_requests = getattr(turn_result, "tool_requests", []) or []
            for tool_req in tool_requests:
                tool_req.jobId = self.job_id
                tool_req.threadId = self.thread_id
                tool_req.conversationId = conversation_id or target_msg.get("conversationId") or self.thread_id
                tool_req.parentMessageId = target_msg.get("id")
                tool_req.requester = {"id": target_agent, "kind": "agent", "displayName": target_agent.capitalize()}

                tool_res = self.tool_registry.execute(
                    request=tool_req,
                    worktree_dir=target_wt,
                    job_config=self.spec,
                    capability_registry=self.capability_registry,
                    publisher=default_publisher,
                    job_id=self.job_id,
                )

                res_text = ""
                if tool_res.output and isinstance(tool_res.output, dict) and "stdout" in tool_res.output:
                    res_text = tool_res.output["stdout"]
                elif tool_res.output:
                    res_text = json.dumps(tool_res.output)
                elif tool_res.error:
                    res_text = f"Error: {tool_res.error}"
                else:
                    res_text = f"Status: {tool_res.status}"

                self._record_message(
                    from_actor={"id": tool_req.toolId, "kind": "tool", "displayName": tool_req.toolId},
                    to_actors=[{"id": target_agent, "kind": "agent", "displayName": target_agent.capitalize()}],
                    kind="tool_result",
                    intent="tool_result",
                    text=res_text,
                    conversation_id=tool_req.conversationId,
                    reply_to=target_msg.get("id"),
                    metadata={
                        "requestId": tool_req.id,
                        "toolId": tool_req.toolId,
                        "status": tool_res.status,
                        "error": tool_res.error,
                    },
                )

            # Acknowledge consumed incoming messages after successful execution
            for mid in target_consumed_ids:
                if default_publisher and default_publisher.enabled:
                    default_publisher.acknowledge_message(target_agent, mid)
                self._consumed_message_ids.add(mid)

        # Emit conversation.completed if natural exit occurred and limit was not reached
        if not limit_reached and phase_turns > 0:
            if default_publisher:
                default_publisher.publish(
                    source_id="hermes_runner",
                    source_kind="runtime",
                    kind="conversation.completed",
                    detail=f"A2A conversation {conversation_id or 'default'} completed ({phase_turns} turns executed)",
                    job_id=self.job_id,
                    metadata={
                        "conversationId": conversation_id,
                        "turnsExecuted": phase_turns,
                        "totalJobTurns": self.job_a2a_turns,
                    },
                )

    def run_tests_in_venv(self):
        self.logger.info("\n=== Running Controller Verification & Pytest Suite ===")
        integration_dir = self.worktree_root / "integration"
        venv_dir = self.run_dir / "venv"

        self.logger.info(f"Creating isolated Python virtual environment at {venv_dir}")
        self.run_cmd([sys.executable, "-m", "venv", str(venv_dir)])

        venv_python = self._venv_python(venv_dir)

        req_file = integration_dir / "requirements.txt"
        if req_file.exists():
            self.logger.info(f"Installing dependencies from {req_file}")
            self.run_cmd(
                [str(venv_python), "-m", "pip", "install", "--no-cache-dir", "-r", str(req_file)],
                cwd=integration_dir,
            )

        self.logger.info("Executing pytest suite...")
        try:
            test_res = self.run_cmd([str(venv_python), "-m", "pytest", "-v"], cwd=integration_dir)
            self.logger.info("Pytest suite passed successfully!")
            self.run_summary["test_results"] = {
                "status": "PASSED",
                "output": test_res.stdout
            }
        except SprintRunnerError as e:
            self.logger.error("Pytest suite execution failed!")
            self.run_summary["test_results"] = {
                "status": "FAILED",
                "error": str(e)
            }
            raise SprintRunnerError("FAILED_TESTS", f"Pytest suite failed in integration worktree: {e}")

    def run_verification(self):
        """Run spec-defined final verification sequentially without a shell."""
        self.logger.info("\n=== Running Generic Verification Pipeline ===")
        integration_dir = self.worktree_root / "integration"
        self.run_summary["verification_status"] = "RUNNING"

        for index, step in enumerate(self.verification_steps, start=1):
            name = step["name"]
            cwd = self._resolve_verification_cwd(step, integration_dir)
            result_record = {"name": name, "status": "FAILED"}
            safe_name = "".join(
                character if character.isalnum() or character in "-_" else "_"
                for character in name
            ) or "step"
            stdout_file = self.run_dir / (
                f"verification_{index:02d}_{safe_name}_stdout.log"
            )
            stderr_file = self.run_dir / (
                f"verification_{index:02d}_{safe_name}_stderr.log"
            )

            if not cwd.is_dir():
                self.run_summary["verification_results"].append(result_record)
                self.run_summary["verification_status"] = "FAILED"
                self._invalid_verification(
                    f"verification step '{name}' cwd does not exist or is not a directory"
                )

            self.logger.info("Running verification step %s: %s", index, name)
            try:
                result = self.run_cmd(
                    step["command"],
                    cwd=cwd,
                    timeout=step["timeout_seconds"],
                    check=False,
                )
            except (OSError, SprintRunnerError) as error:
                stdout_file.write_text("", encoding="utf-8")
                stderr_file.write_text(str(error), encoding="utf-8")
                self.run_summary["verification_results"].append(result_record)
                self.run_summary["verification_status"] = "FAILED"
                raise SprintRunnerError(
                    "FAILED_VERIFICATION",
                    f"Verification step '{name}' could not complete: {error}",
                ) from error

            stdout_file.write_text(result.stdout or "", encoding="utf-8")
            stderr_file.write_text(result.stderr or "", encoding="utf-8")
            if result.returncode != 0:
                self.run_summary["verification_results"].append(result_record)
                self.run_summary["verification_status"] = "FAILED"
                raise SprintRunnerError(
                    "FAILED_VERIFICATION",
                    f"Verification step '{name}' failed with exit code {result.returncode}",
                )

            result_record["status"] = "PASSED"
            self.run_summary["verification_results"].append(result_record)

        self.run_summary["verification_status"] = "PASSED"

    @staticmethod
    def _venv_python(venv_dir, platform_name=None):
        platform_name = platform_name or os.name
        if platform_name == "nt":
            return venv_dir / "Scripts" / "python.exe"
        return venv_dir / "bin" / "python"

    def finalize(self):
        # Validate that all phases succeeded and pytest passed before granting READY_FOR_REVIEW
        for p in self.run_summary["phases"]:
            if p["status"] != "SUCCESS":
                raise SprintRunnerError(
                    "FAILED_INCOMPLETE_PHASE",
                    f"Phase '{p['phase']}' did not reach SUCCESS status (was {p['status']})."
                )

        if self.verification_steps:
            if self.run_summary.get("verification_status") != "PASSED":
                raise SprintRunnerError(
                    "FAILED_VERIFICATION",
                    "Generic verification failed or did not run.",
                )
        elif not self.run_summary.get("test_results") or self.run_summary["test_results"].get("status") != "PASSED":
            raise SprintRunnerError(
                "FAILED_TESTS",
                "Pytest validation failed or did not run."
            )

        integration_dir = self.worktree_root / "integration"
        sha_res = self.run_cmd(["git", "rev-parse", "HEAD"], cwd=integration_dir)
        self.run_summary["integration_commit"] = sha_res.stdout.strip()
        self.run_summary["status"] = "READY_FOR_REVIEW"
        self.run_summary["end_time"] = datetime.now().isoformat()

        # Record final artifacts & verification result message (Phase 5)
        integration_commit = self.run_summary["integration_commit"]
        art_integration = {
            "id": "art_integration_commit",
            "type": "git_commit",
            "label": f"Integration Commit ({integration_commit[:7]})",
            "ref": integration_commit,
            "jobId": self.job_id,
        }
        self._record_artifact(art_integration)

        art_summary = {
            "id": "art_summary",
            "type": "run_summary",
            "label": "Run Summary Report",
            "ref": str(self.summary_file),
            "jobId": self.job_id,
        }
        self._record_artifact(art_summary)

        art_log = {
            "id": "art_log",
            "type": "log",
            "label": "Runner Execution Log",
            "ref": str(self.log_file),
            "jobId": self.job_id,
        }
        self._record_artifact(art_log)

        verifier_agent = self.spec.get("phases", [])[-1]["agent"] if self.spec.get("phases") else "hermes_runner"
        verification_passed = len([v for v in self.run_summary.get("verification_results", []) if v.get("status") == "PASSED"])
        ver_text = f"Verification passed: {verification_passed} checks passed, 0 failed." if verification_passed else "Verification completed successfully."
        
        self._record_message(
            from_actor={"id": verifier_agent, "kind": "agent", "displayName": verifier_agent.capitalize()},
            to_actors=[
                {"id": "lysstack", "kind": "runtime", "displayName": "LysStack"},
                {"id": "hermes_runner", "kind": "runtime", "displayName": "Hermes Runner"},
            ],
            kind="verification_result",
            intent="verification_result",
            text=ver_text,
            artifact_refs=[art_integration, art_summary],
        )
        
        self.logger.info("\n==========================================")
        self.logger.info(f"Sprint {self.sprint_id} Workflow Complete!")
        self.logger.info(f"Final Status: READY_FOR_REVIEW")
        self.logger.info(f"Integration Commit: {self.run_summary['integration_commit']}")
        self.logger.info("==========================================\n")

    def preflight(self):
        """Validate sprint readiness without running or integrating agent work."""
        self.validate_execution_plan()
        self.prepare_environment()
        self.validate_preflight_worktree_config()
        self.run_summary["status"] = "DRY_RUN_READY"
        self.run_summary["end_time"] = datetime.now().isoformat()
        self.logger.info("Dry-run preflight complete. Final Status: DRY_RUN_READY")

    def export_sanitized_report(self, report_path=None):
        """Write deterministic run evidence without prompts, logs, or errors."""
        destination_value = report_path or self.report_path
        if destination_value is None:
            raise ValueError("A report path is required for sanitized export")
        destination = Path(destination_value).resolve()
        test_results = self.run_summary.get("test_results") or {}
        sanitized = {
            "sprint_id": self.sprint_id,
            "status": self.run_summary.get("status"),
            "phases": [
                {
                    "phase": phase.get("phase"),
                    "agent": phase.get("agent"),
                    "status": phase.get("status"),
                    "changed_files_count": phase.get("changed_files_count"),
                    **(
                        {"role": phase.get("role")}
                        if phase.get("role")
                        else {}
                    ),
                    **(
                        {"integrated": phase.get("integrated")}
                        if "integrated" in phase
                        else {}
                    ),
                    **(
                        {"handoff": phase.get("handoff")}
                        if phase.get("handoff")
                        else {}
                    ),
                    **(
                        {"backend": phase.get("backend")}
                        if phase.get("backend")
                        else {}
                    ),
                }
                for phase in self.run_summary.get("phases", [])
            ],
            "test_status": test_results.get("status"),
            "integration_commit": self.run_summary.get("integration_commit"),
        }
        if self.verification_steps:
            sanitized["verification_status"] = self.run_summary.get(
                "verification_status"
            )
            sanitized["verification"] = [
                {
                    "name": result.get("name"),
                    "status": result.get("status"),
                }
                for result in self.run_summary.get("verification_results", [])
            ]
        if self.context_files:
            sanitized["context"] = {
                "files_count": len(self.context_files),
                "bytes": self.context_bytes,
            }
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(sanitized, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.logger.info("Sanitized run report written to %s", destination)
        return destination

    def execute(self):
        participants = [
            {"id": p["agent"], "kind": "agent", "displayName": p["agent"].capitalize()}
            for p in self.spec.get("phases", [])
        ]
        participants.append({"id": "hermes_runner", "kind": "runtime", "displayName": "Hermes Runner"})
        participants.append({"id": "lysstack", "kind": "runtime", "displayName": "LysStack"})

        if default_publisher:
            default_publisher.publish_thread(
                self.thread_id,
                job_id=self.job_id,
                title=self.spec.get("name", f"Hermes Sprint {self.sprint_id}"),
                participants=participants,
            )
            default_publisher.publish(
                source_id="hermes_runner",
                source_kind="runtime",
                kind="job.created",
                detail=f"Sprint {self.sprint_id} initialized",
                job_id=self.job_id,
                metadata={
                    "sprintId": self.sprint_id,
                    "title": self.spec.get("name", f"Hermes Sprint {self.sprint_id}"),
                    "repository": str(self.target_repo.name),
                    "branch": self.spec.get("target_branch", f"hermes/{self.sprint_id}/integration"),
                    "phases": self.spec.get("phases", []),
                },
            )
            default_publisher.publish(
                source_id="hermes_runner",
                source_kind="runtime",
                kind="job.started",
                detail=f"Sprint {self.sprint_id} execution started",
                job_id=self.job_id,
                metadata={"sprintId": self.sprint_id},
            )

        try:
            if self.dry_run:
                self.preflight()
            else:
                self.prepare_environment()
                for phase_index, phase in enumerate(self.spec.get("phases", []), start=1):
                    self.execute_phase(phase, phase_index=phase_index)
                if self.verification_steps:
                    self.run_verification()
                else:
                    self.run_tests_in_venv()
                self.finalize()
        except SprintRunnerError as e:
            self.run_summary["status"] = e.code
            self.run_summary["end_time"] = datetime.now().isoformat()
            self.run_summary["errors"].append({"code": e.code, "message": e.message})
            self.logger.error(f"FAIL-FAST TRIGGERED: [{e.code}] {e.message}")
            if default_publisher:
                default_publisher.publish(
                    source_id="hermes_runner",
                    source_kind="runtime",
                    kind="job.failed",
                    detail=f"Sprint {self.sprint_id} failed: [{e.code}] {e.message}",
                    job_id=self.job_id,
                    metadata={"sprintId": self.sprint_id, "error": e.message, "code": e.code},
                )
        finally:
            sprint_succeeded = self.run_summary["status"] in {"READY_FOR_REVIEW", "DRY_RUN_READY"}
            if sprint_succeeded and default_publisher:
                default_publisher.publish(
                    source_id="hermes_runner",
                    source_kind="runtime",
                    kind="job.completed",
                    detail=f"Sprint {self.sprint_id} completed successfully",
                    job_id=self.job_id,
                    metadata={
                        "sprintId": self.sprint_id,
                        "integrationCommit": self.run_summary.get("integration_commit"),
                    },
                )

            for backend in self._backend_cache.values():
                try:
                    backend.cleanup(success=sprint_succeeded)
                except SprintRunnerError as cleanup_error:
                    self.logger.error(
                        "Backend cleanup failed: [%s] %s",
                        cleanup_error.code,
                        cleanup_error.message,
                    )
            with open(self.summary_file, "w", encoding="utf-8") as f:
                json.dump(self.run_summary, f, indent=2)
            self.logger.info(f"Run summary written to {self.summary_file}")
            if self.report_path is not None:
                self.export_sanitized_report()

        return self.run_summary["status"] in {"READY_FOR_REVIEW", "DRY_RUN_READY"}


def main():
    parser = argparse.ArgumentParser(description="Hermes Sprint Workflow Runner")
    parser.add_argument("--spec", default="sprints/lab-s04.json", help="Path to sprint JSON specification")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run configuration/worktree preflight without agents or verification",
    )
    parser.add_argument("--skip-agent-execution", action="store_true", help="Skip invoking external agent CLI")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose debug logging")
    parser.add_argument(
        "--backend",
        help="Globally override the sprint execution backend unless a phase overrides it",
    )
    parser.add_argument(
        "--export-report",
        nargs="?",
        const=True,
        default=False,
        metavar="PATH",
        help=(
            "Export sanitized evidence; defaults to "
            "reports/<sprint-id>/run-summary.json"
        ),
    )

    args = parser.parse_args()
    
    runner = HermesSprintRunner(
        spec_path=args.spec,
        dry_run=args.dry_run,
        skip_agent_exec=args.skip_agent_execution,
        verbose=args.verbose,
        backend_override=args.backend,
        export_report=args.export_report,
    )
    
    success = runner.execute()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
