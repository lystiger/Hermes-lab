from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
from artifact_registry import ArtifactRef
from normalization import normalize_agent_id

logger = logging.getLogger("hermes.message_store")


@dataclass
class ActorRefDTO:
    id: str
    kind: str  # "agent" | "system" | "runtime" | "tool" | "operator"
    displayName: str
    accentColor: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "displayName": self.displayName,
            "accentColor": self.accentColor,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActorRefDTO":
        raw_id = data.get("id", "unknown")
        kind = data.get("kind", "agent")
        normalized_id = normalize_agent_id(raw_id) if kind == "agent" else raw_id
        return cls(
            id=normalized_id,
            kind=kind,
            displayName=data.get("displayName") or normalized_id.capitalize(),
            accentColor=data.get("accentColor"),
        )


@dataclass
class MessageDTO:
    id: str
    threadId: str
    from_actor: ActorRefDTO
    to_actors: List[ActorRefDTO]
    kind: str
    text: str
    intent: Optional[str] = None
    jobId: Optional[str] = None
    phaseId: Optional[str] = None
    artifactRefs: List[ArtifactRef] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    createdAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "threadId": self.threadId,
            "from": self.from_actor.to_dict(),
            "to": [a.to_dict() for a in self.to_actors],
            "kind": self.kind,
            "text": self.text,
            "intent": self.intent,
            "jobId": self.jobId,
            "phaseId": self.phaseId,
            "artifactRefs": [a.to_dict() for a in self.artifactRefs],
            "metadata": self.metadata,
            "createdAt": self.createdAt,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageDTO":
        from_data = data.get("from") or {}
        from_actor = ActorRefDTO.from_dict(from_data)

        to_data = data.get("to") or []
        to_actors = [ActorRefDTO.from_dict(item) for item in to_data]

        raw_artifacts = data.get("artifactRefs") or []
        artifact_refs = [
            ArtifactRef.from_dict(a) if isinstance(a, dict) else a
            for a in raw_artifacts
        ]

        return cls(
            id=data.get("id", ""),
            threadId=data.get("threadId", ""),
            from_actor=from_actor,
            to_actors=to_actors,
            kind=data.get("kind", "status"),
            text=data.get("text", ""),
            intent=data.get("intent"),
            jobId=data.get("jobId"),
            phaseId=data.get("phaseId"),
            artifactRefs=artifact_refs,
            metadata=data.get("metadata") or {},
            createdAt=data.get("createdAt") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass
class ThreadDTO:
    id: str
    jobId: Optional[str] = None
    title: Optional[str] = None
    participants: List[ActorRefDTO] = field(default_factory=list)
    createdAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updatedAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "jobId": self.jobId,
            "title": self.title,
            "participants": [p.to_dict() for p in self.participants],
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThreadDTO":
        participants_data = data.get("participants") or []
        participants = [ActorRefDTO.from_dict(p) for p in participants_data]
        return cls(
            id=data.get("id", ""),
            jobId=data.get("jobId"),
            title=data.get("title"),
            participants=participants,
            createdAt=data.get("createdAt") or datetime.now(timezone.utc).isoformat(),
            updatedAt=data.get("updatedAt") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass
class MailboxEntryDTO:
    messageId: str
    recipientId: str
    state: str  # "PENDING" | "DELIVERED" | "ACKNOWLEDGED"
    receivedAt: str
    acknowledgedAt: Optional[str] = None
    message: Optional[MessageDTO] = None

    def to_dict(self) -> Dict[str, Any]:
        res = {
            "messageId": self.messageId,
            "recipientId": self.recipientId,
            "state": self.state,
            "receivedAt": self.receivedAt,
            "acknowledgedAt": self.acknowledgedAt,
        }
        if self.message:
            res["message"] = self.message.to_dict()
        return res


class MessageStore:
    """
    In-memory indexed and persistent store for LysStack operational threads, messages, and mailboxes.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._threads: Dict[str, ThreadDTO] = {}
        self._messages: Dict[str, MessageDTO] = {}
        self._thread_messages: Dict[str, List[str]] = {}
        self._job_threads: Dict[str, List[str]] = {}
        self._inboxes: Dict[str, List[MailboxEntryDTO]] = {}

    def create_thread(self, thread: ThreadDTO) -> ThreadDTO:
        with self._lock:
            self._threads[thread.id] = thread
            if thread.id not in self._thread_messages:
                self._thread_messages[thread.id] = []
            if thread.jobId:
                if thread.jobId not in self._job_threads:
                    self._job_threads[thread.jobId] = []
                if thread.id not in self._job_threads[thread.jobId]:
                    self._job_threads[thread.jobId].append(thread.id)
            return thread

    def get_thread(self, thread_id: str) -> Optional[ThreadDTO]:
        with self._lock:
            return self._threads.get(thread_id)

    def list_threads(
        self,
        job_id: Optional[str] = None,
        participant: Optional[str] = None,
        limit: int = 50,
    ) -> List[ThreadDTO]:
        with self._lock:
            threads = list(self._threads.values())

        if job_id:
            threads = [t for t in threads if t.jobId == job_id]

        if participant:
            norm_part = normalize_agent_id(participant)
            threads = [
                t for t in threads
                if any(p.id == norm_part or p.id == participant for p in t.participants)
            ]

        # Sort newest updatedAt first
        threads.sort(key=lambda t: t.updatedAt or t.createdAt or "", reverse=True)
        return threads[:limit]

    def append_message(self, message: MessageDTO) -> MessageDTO:
        with self._lock:
            self._messages[message.id] = message

            # Ensure thread exists or create default
            thread = self._threads.get(message.threadId)
            if not thread:
                participants = [message.from_actor] + [
                    to for to in message.to_actors
                    if to.id != message.from_actor.id
                ]
                thread = ThreadDTO(
                    id=message.threadId,
                    jobId=message.jobId,
                    title=f"Thread {message.threadId}",
                    participants=participants,
                    createdAt=message.createdAt,
                    updatedAt=message.createdAt,
                )
                self._threads[thread.id] = thread
                self._thread_messages[thread.id] = []
                if thread.jobId:
                    if thread.jobId not in self._job_threads:
                        self._job_threads[thread.jobId] = []
                    if thread.id not in self._job_threads[thread.jobId]:
                        self._job_threads[thread.jobId].append(thread.id)
            else:
                # Add any new participants
                existing_ids = {p.id for p in thread.participants}
                if message.from_actor.id not in existing_ids:
                    thread.participants.append(message.from_actor)
                    existing_ids.add(message.from_actor.id)
                for to in message.to_actors:
                    if to.id not in existing_ids:
                        thread.participants.append(to)
                        existing_ids.add(to.id)
                thread.updatedAt = message.createdAt

            if message.threadId not in self._thread_messages:
                self._thread_messages[message.threadId] = []
            if message.id not in self._thread_messages[message.threadId]:
                self._thread_messages[message.threadId].append(message.id)

            # Mailbox entries for recipients
            for to in message.to_actors:
                recipient_id = to.id
                if recipient_id not in self._inboxes:
                    self._inboxes[recipient_id] = []
                entry = MailboxEntryDTO(
                    messageId=message.id,
                    recipientId=recipient_id,
                    state="DELIVERED",
                    receivedAt=message.createdAt,
                    message=message,
                )
                self._inboxes[recipient_id].append(entry)

            return message

    def get_message(self, message_id: str) -> Optional[MessageDTO]:
        with self._lock:
            return self._messages.get(message_id)

    def list_messages(
        self,
        thread_id: str,
        limit: int = 50,
        after_id: Optional[str] = None,
    ) -> List[MessageDTO]:
        with self._lock:
            msg_ids = list(self._thread_messages.get(thread_id, []))
            messages = [self._messages[mid] for mid in msg_ids if mid in self._messages]

        if after_id:
            try:
                idx = next(i for i, m in enumerate(messages) if m.id == after_id)
                messages = messages[idx + 1 :]
            except StopIteration:
                pass

        if limit and len(messages) > limit:
            messages = messages[-limit:]

        return messages

    def list_inbox(
        self,
        recipient_id: str,
        state: Optional[str] = None,
        limit: int = 50,
    ) -> List[MailboxEntryDTO]:
        norm_id = normalize_agent_id(recipient_id)
        with self._lock:
            entries = list(self._inboxes.get(norm_id, []))
            if norm_id != recipient_id:
                entries.extend(self._inboxes.get(recipient_id, []))

        if state:
            entries = [e for e in entries if e.state.upper() == state.upper()]

        entries.sort(key=lambda e: e.receivedAt, reverse=True)
        return entries[:limit]

    def acknowledge_message(self, message_id: str, recipient_id: str) -> bool:
        norm_id = normalize_agent_id(recipient_id)
        with self._lock:
            entries = self._inboxes.get(norm_id, [])
            for entry in entries:
                if entry.messageId == message_id:
                    entry.state = "ACKNOWLEDGED"
                    entry.acknowledgedAt = datetime.now(timezone.utc).isoformat()
                    return True
        return False

    def recover_from_runs(self, runs_root: Path) -> None:
        """Recovers historical threads and messages from messages.jsonl files in hermes-runs directory."""
        if not runs_root.exists():
            return

        try:
            for run_dir in sorted(runs_root.glob("*_*")):
                if not run_dir.is_dir():
                    continue

                msg_file = run_dir / "messages.jsonl"
                if not msg_file.exists():
                    continue

                try:
                    with open(msg_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            data = json.loads(line)
                            msg = MessageDTO.from_dict(data)
                            self.append_message(msg)
                except Exception as exc:
                    logger.debug("Failed recovering messages from %s: %s", msg_file, exc)
        except Exception as exc:
            logger.warning("Failed during startup message recovery: %s", exc)


message_store = MessageStore()
