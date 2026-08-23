from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
from artifacts.artifact_registry import ArtifactRef
from capabilities.normalization import normalize_agent_id

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
    conversationId: Optional[str] = None
    replyTo: Optional[str] = None
    correlationId: Optional[str] = None
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
            "conversationId": self.conversationId,
            "replyTo": self.replyTo,
            "correlationId": self.correlationId,
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
            conversationId=data.get("conversationId"),
            replyTo=data.get("replyTo"),
            correlationId=data.get("correlationId"),
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
    receivedAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledgedAt: Optional[str] = None
    message: Optional[MessageDTO] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "messageId": self.messageId,
            "recipientId": self.recipientId,
            "state": self.state,
            "receivedAt": self.receivedAt,
            "acknowledgedAt": self.acknowledgedAt,
            "message": self.message.to_dict() if self.message else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MailboxEntryDTO":
        msg_data = data.get("message")
        msg_obj = MessageDTO.from_dict(msg_data) if isinstance(msg_data, dict) else None
        return cls(
            messageId=data.get("messageId", ""),
            recipientId=data.get("recipientId", ""),
            state=data.get("state", "DELIVERED"),
            receivedAt=data.get("receivedAt") or datetime.now(timezone.utc).isoformat(),
            acknowledgedAt=data.get("acknowledgedAt"),
            message=msg_obj,
        )


class MessageStore:
    """
    In-memory and JSONL-persisted store for operational threads, messages, and mailboxes.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._threads: Dict[str, ThreadDTO] = {}
        self._messages: Dict[str, MessageDTO] = {}
        self._thread_messages: Dict[str, List[str]] = {}  # threadId -> list of messageIds
        self._job_threads: Dict[str, List[str]] = {}      # jobId -> list of threadIds
        self._inboxes: Dict[str, List[MailboxEntryDTO]] = {}  # recipientId -> list of mailbox entries

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
            if job_id:
                thread_ids = self._job_threads.get(job_id, [])
                threads = [self._threads[tid] for tid in thread_ids if tid in self._threads]
            else:
                threads = list(self._threads.values())

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
        conversation_id: Optional[str] = None,
    ) -> List[MessageDTO]:
        with self._lock:
            msg_ids = list(self._thread_messages.get(thread_id, []))
            messages = [self._messages[mid] for mid in msg_ids if mid in self._messages]

        if conversation_id:
            messages = [m for m in messages if m.conversationId == conversation_id]

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
        job_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        chronological: bool = False,
        conversation_id: Optional[str] = None,
    ) -> List[MailboxEntryDTO]:
        norm_id = normalize_agent_id(recipient_id)
        with self._lock:
            seen_ids = set()
            entries = []
            for e in self._inboxes.get(norm_id, []):
                if e.messageId not in seen_ids:
                    seen_ids.add(e.messageId)
                    entries.append(e)
            if norm_id != recipient_id:
                for e in self._inboxes.get(recipient_id, []):
                    if e.messageId not in seen_ids:
                        seen_ids.add(e.messageId)
                        entries.append(e)

        if state:
            entries = [e for e in entries if e.state.upper() == state.upper()]

        if job_id:
            entries = [
                e for e in entries
                if e.message and (e.message.jobId == job_id or (e.message.threadId and job_id in e.message.threadId))
            ]

        if thread_id:
            entries = [e for e in entries if e.message and e.message.threadId == thread_id]

        if conversation_id:
            entries = [e for e in entries if e.message and e.message.conversationId == conversation_id]

        if chronological:
            entries.sort(key=lambda e: e.receivedAt or "")
        else:
            entries.sort(key=lambda e: e.receivedAt or "", reverse=True)

        return entries[:limit]

    def acknowledge_message(self, message_id: str, recipient_id: str) -> bool:
        norm_id = normalize_agent_id(recipient_id)
        with self._lock:
            found = False
            for bucket_key in {norm_id, recipient_id}:
                entries = self._inboxes.get(bucket_key, [])
                for entry in entries:
                    if entry.messageId == message_id:
                        entry.state = "ACKNOWLEDGED"
                        entry.acknowledgedAt = datetime.now(timezone.utc).isoformat()
                        found = True
            return found

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

                with open(msg_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg_dict = json.loads(line)
                            msg_dto = MessageDTO.from_dict(msg_dict)
                            self.append_message(msg_dto)
                        except Exception as parse_err:
                            logger.warning("Failed parsing message line in %s: %s", msg_file, parse_err)
        except Exception as e:
            logger.warning("Failed recovering messages from runs: %s", e)


message_store = MessageStore()
