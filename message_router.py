from datetime import datetime, timezone
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Set, Union
from artifact_registry import ArtifactRef, artifact_registry
from event_bus import event_bus
from message_store import (
    ActorRefDTO,
    MessageDTO,
    ThreadDTO,
    MailboxEntryDTO,
    message_store,
)
from normalization import normalize_agent_id

logger = logging.getLogger("hermes.message_router")


class MessageRouter:
    """
    Control-plane service that governs operational messaging, thread lifecycles,
    structured A2A conversation turns, artifact association, and event broadcasting for LysStack.
    """

    def __init__(self, store=None, registry=None, bus=None):
        self.store = store or message_store
        self.registry = registry or artifact_registry
        self.bus = bus or event_bus
        self._msg_counter = 0
        self._seen_conversations: Set[str] = set()
        self._lock = threading.Lock()

    def generate_message_id(self) -> str:
        with self._lock:
            self._msg_counter += 1
            ts_ms = int(time.time() * 1000)
            return f"msg_{ts_ms}_{self._msg_counter:04d}"

    def build_actor_ref(
        self,
        actor: Union[str, Dict[str, Any], ActorRefDTO],
        kind: str = "agent",
    ) -> ActorRefDTO:
        if isinstance(actor, ActorRefDTO):
            return actor
        if isinstance(actor, dict):
            return ActorRefDTO.from_dict(actor)
        if isinstance(actor, str):
            normalized = normalize_agent_id(actor) if kind == "agent" else actor.lower()
            return ActorRefDTO(
                id=normalized,
                kind=kind,
                displayName=normalized.capitalize(),
            )
        return ActorRefDTO(id="unknown", kind=kind, displayName="Unknown")

    def create_thread(
        self,
        thread_id: str,
        job_id: Optional[str] = None,
        title: Optional[str] = None,
        participants: Optional[List[Union[str, Dict[str, Any], ActorRefDTO]]] = None,
    ) -> ThreadDTO:
        participant_dtos: List[ActorRefDTO] = []
        if participants:
            for p in participants:
                participant_dtos.append(self.build_actor_ref(p))

        thread = ThreadDTO(
            id=thread_id,
            jobId=job_id,
            title=title or f"Job Thread {thread_id}",
            participants=participant_dtos,
            createdAt=datetime.now(timezone.utc).isoformat(),
            updatedAt=datetime.now(timezone.utc).isoformat(),
        )
        created = self.store.create_thread(thread)

        # Broadcast thread.created event
        self.bus.publish(
            source_id="lysstack",
            source_kind="runtime",
            source_name="LysStack MessageRouter",
            kind="thread.created",
            detail=f"Operational thread created: {thread_id}",
            job_id=job_id,
            metadata={
                "threadId": thread_id,
                "jobId": job_id,
                "title": created.title,
                "participants": [p.to_dict() for p in created.participants],
            },
        )
        return created

    def send_message(
        self,
        thread_id: str,
        from_actor: Union[str, Dict[str, Any], ActorRefDTO],
        to_actors: List[Union[str, Dict[str, Any], ActorRefDTO]],
        kind: str,
        text: str,
        intent: Optional[str] = None,
        conversation_id: Optional[str] = None,
        reply_to: Optional[str] = None,
        correlation_id: Optional[str] = None,
        job_id: Optional[str] = None,
        phase_id: Optional[str] = None,
        artifact_refs: Optional[List[Union[Dict[str, Any], ArtifactRef]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        custom_id: Optional[str] = None,
    ) -> MessageDTO:
        # Validate sender and recipients
        from_dto = self.build_actor_ref(from_actor)
        to_dtos = [self.build_actor_ref(to) for to in to_actors] if to_actors else []

        if not to_dtos:
            to_dtos = [ActorRefDTO(id="lysstack", kind="runtime", displayName="LysStack")]

        # Process artifact references
        resolved_artifacts: List[ArtifactRef] = []
        if artifact_refs:
            for art in artifact_refs:
                if isinstance(art, ArtifactRef):
                    self.registry.register(art)
                    resolved_artifacts.append(art)
                elif isinstance(art, dict):
                    ref_obj = ArtifactRef.from_dict(art)
                    if job_id and not ref_obj.jobId:
                        ref_obj.jobId = job_id
                    if phase_id and not ref_obj.phaseId:
                        ref_obj.phaseId = phase_id
                    self.registry.register(ref_obj)
                    resolved_artifacts.append(ref_obj)

        msg_id = custom_id or self.generate_message_id()
        now_iso = datetime.now(timezone.utc).isoformat()

        message = MessageDTO(
            id=msg_id,
            threadId=thread_id,
            from_actor=from_dto,
            to_actors=to_dtos,
            kind=kind,
            text=text,
            intent=intent,
            conversationId=conversation_id,
            replyTo=reply_to,
            correlationId=correlation_id,
            jobId=job_id,
            phaseId=phase_id,
            artifactRefs=resolved_artifacts,
            metadata=metadata or {},
            createdAt=now_iso,
        )

        stored = self.store.append_message(message)

        # Emit runtime event message.created
        to_names = ", ".join([t.displayName for t in to_dtos])
        self.bus.publish(
            source_id=from_dto.id,
            source_kind=from_dto.kind,
            source_name=from_dto.displayName,
            kind="message.created",
            detail=f"{from_dto.displayName} → {to_names}: [{kind}] {text[:60]}",
            job_id=job_id,
            metadata={
                "messageId": stored.id,
                "threadId": stored.threadId,
                "conversationId": stored.conversationId,
                "replyTo": stored.replyTo,
                "correlationId": stored.correlationId,
                "jobId": stored.jobId,
                "phaseId": stored.phaseId,
                "kind": stored.kind,
                "intent": stored.intent,
                "from": from_dto.to_dict(),
                "to": [t.to_dict() for t in to_dtos],
                "artifactRefs": [a.to_dict() for a in resolved_artifacts],
                "text": stored.text,
            },
            accent_color=from_dto.accentColor,
        )

        # Emit conversation lifecycle events
        if conversation_id:
            with self._lock:
                is_first_in_conv = conversation_id not in self._seen_conversations
                self._seen_conversations.add(conversation_id)

            if is_first_in_conv:
                self.bus.publish(
                    source_id=from_dto.id,
                    source_kind=from_dto.kind,
                    source_name=from_dto.displayName,
                    kind="conversation.started",
                    detail=f"Conversation started: {conversation_id} by {from_dto.displayName}",
                    job_id=job_id,
                    metadata={
                        "conversationId": conversation_id,
                        "threadId": thread_id,
                        "jobId": job_id,
                        "firstMessageId": stored.id,
                        "from": from_dto.to_dict(),
                        "to": [t.to_dict() for t in to_dtos],
                    },
                )

            # Turn event
            self.bus.publish(
                source_id=from_dto.id,
                source_kind=from_dto.kind,
                source_name=from_dto.displayName,
                kind="conversation.turn",
                detail=f"Conversation turn in {conversation_id}: {from_dto.displayName} [{intent or kind}]",
                job_id=job_id,
                metadata={
                    "conversationId": conversation_id,
                    "threadId": thread_id,
                    "jobId": job_id,
                    "messageId": stored.id,
                    "from": from_dto.to_dict(),
                    "to": [t.to_dict() for t in to_dtos],
                    "intent": intent,
                    "replyTo": reply_to,
                    "correlationId": correlation_id,
                },
            )

        return stored

    def get_thread(self, thread_id: str) -> Optional[ThreadDTO]:
        return self.store.get_thread(thread_id)

    def list_threads(
        self,
        job_id: Optional[str] = None,
        participant: Optional[str] = None,
        limit: int = 50,
    ) -> List[ThreadDTO]:
        return self.store.list_threads(job_id=job_id, participant=participant, limit=limit)

    def list_messages(
        self,
        thread_id: str,
        limit: int = 50,
        after_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> List[MessageDTO]:
        return self.store.list_messages(
            thread_id=thread_id,
            limit=limit,
            after_id=after_id,
            conversation_id=conversation_id,
        )

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
        return self.store.list_inbox(
            recipient_id=recipient_id,
            state=state,
            limit=limit,
            job_id=job_id,
            thread_id=thread_id,
            chronological=chronological,
            conversation_id=conversation_id,
        )

    def acknowledge(self, message_id: str, recipient_id: str) -> bool:
        success = self.store.acknowledge_message(message_id=message_id, recipient_id=recipient_id)
        if success:
            self.bus.publish(
                source_id=recipient_id,
                source_kind="agent",
                kind="message.acknowledged",
                detail=f"Message {message_id} acknowledged by {recipient_id}",
                metadata={"messageId": message_id, "recipientId": recipient_id},
            )
        return success


message_router = MessageRouter()
