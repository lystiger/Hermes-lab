import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Mapping, Optional, Sequence

logger = logging.getLogger("hermes.a2a")

LYSSTACK_A2A_START = "--- LYSSTACK A2A OUTPUT ---"
LYSSTACK_A2A_END = "--- END LYSSTACK A2A OUTPUT ---"

# Schedulable request intents: messages with these intents trigger conversational turns
SCHEDULABLE_INTENTS = {
    "review_request",
    "correction_request",
    "question",
    "verification_request",
    "correction_result",
    "task_request",
}

# Terminal or result intents: convey outcomes or answers without automatically requiring further turns
TERMINAL_INTENTS = {
    "review_result",
    "answer",
    "verification_result",
    "status",
    "task_result",
    "tool_result",
}

# Forbidden keys stripped from A2A output metadata
FORBIDDEN_OUTPUT_KEYS = {
    "permissions",
    "tools",
    "shell",
    "sudo",
    "privileges",
    "allowed_commands",
    "workspace_scope",
    "controller_authority",
}


@dataclass
class A2AOutput:
    intent: str
    to: List[str]
    text: str
    conversationId: Optional[str] = None
    replyTo: Optional[str] = None
    correlationId: Optional[str] = None
    artifactRefs: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "A2AOutput":
        intent = str(data.get("intent", "status")).strip()
        raw_to = data.get("to", [])
        if isinstance(raw_to, str):
            to = [raw_to.strip()] if raw_to.strip() else []
        elif isinstance(raw_to, list):
            to = [str(x).strip() for x in raw_to if str(x).strip()]
        else:
            to = []

        text = str(data.get("text", "")).strip()

        # Sanitize metadata
        raw_meta = data.get("metadata", {})
        meta = {}
        if isinstance(raw_meta, dict):
            for k, v in raw_meta.items():
                if k not in FORBIDDEN_OUTPUT_KEYS:
                    meta[k] = v

        return cls(
            intent=intent,
            to=to,
            text=text,
            conversationId=data.get("conversationId") or data.get("conversation_id"),
            replyTo=data.get("replyTo") or data.get("reply_to"),
            correlationId=data.get("correlationId") or data.get("correlation_id"),
            artifactRefs=data.get("artifactRefs") or data.get("artifact_refs") or [],
            metadata=meta or None,
        )


@dataclass
class AgentTurnResult:
    execution_result: Any
    text: Optional[str] = None
    outgoing_messages: List[A2AOutput] = field(default_factory=list)
    delegation_requests: List[Any] = field(default_factory=list)
    tool_requests: List[Any] = field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None

    @property
    def returncode(self) -> int:
        if self.execution_result and hasattr(self.execution_result, "returncode"):
            rc = getattr(self.execution_result, "returncode")
            if isinstance(rc, int):
                return rc
        return 0

    @property
    def stdout(self) -> str:
        if self.text is not None and isinstance(self.text, str):
            return self.text
        if self.execution_result and hasattr(self.execution_result, "stdout"):
            val = getattr(self.execution_result, "stdout")
            if isinstance(val, str):
                return val
        return ""

    @property
    def stderr(self) -> str:
        if self.execution_result and hasattr(self.execution_result, "stderr"):
            val = getattr(self.execution_result, "stderr")
            if isinstance(val, str):
                return val
        return ""

    @property
    def command(self) -> Sequence[str]:
        if self.execution_result and hasattr(self.execution_result, "command"):
            return getattr(self.execution_result, "command") or ()
        return ()

    @property
    def backend(self) -> str:
        if self.execution_result and hasattr(self.execution_result, "backend"):
            return str(getattr(self.execution_result, "backend"))
        return ""

    @property
    def runtime_metadata(self) -> Mapping[str, Any]:
        if self.execution_result and hasattr(self.execution_result, "runtime_metadata"):
            meta = getattr(self.execution_result, "runtime_metadata")
            if isinstance(meta, dict):
                return meta
        return {}


class A2AOutputParser:
    """
    Production parser for structured agent outputs:
    - A2A messages: LYSSTACK_A2A_START ... LYSSTACK_A2A_END
    - Delegation requests: LYSSTACK_DELEGATION_START ... LYSSTACK_DELEGATION_END
    - Tool requests: LYSSTACK_TOOL_REQUEST_START ... LYSSTACK_TOOL_REQUEST_END
    """

    @classmethod
    def parse(
        cls,
        raw_text: Any,
        execution_result: Any = None,
        strict: bool = False,
        publisher: Any = None,
        job_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> AgentTurnResult:
        if raw_text is None:
            return AgentTurnResult(execution_result=execution_result, text="", outgoing_messages=[])

        # Handle non-string types safely (e.g. MagicMock objects in unit tests)
        if not isinstance(raw_text, str):
            if hasattr(raw_text, "_mock_name") or "Mock" in raw_text.__class__.__name__:
                return AgentTurnResult(execution_result=execution_result, text="", outgoing_messages=[])
            try:
                raw_text = str(raw_text)
            except Exception:
                return AgentTurnResult(execution_result=execution_result, text="", outgoing_messages=[])

        outgoing_messages: List[A2AOutput] = []
        delegation_requests: List[Any] = []
        tool_requests: List[Any] = []

        # 1. Parse A2A Output Blocks
        a2a_pattern = re.compile(
            rf"{re.escape(LYSSTACK_A2A_START)}\s*(.*?)\s*{re.escape(LYSSTACK_A2A_END)}",
            re.DOTALL,
        )
        a2a_matches = a2a_pattern.findall(raw_text)

        for block in a2a_matches:
            cleaned = block.strip()
            if not cleaned:
                continue

            try:
                parsed_json = json.loads(cleaned)
            except Exception as json_err:
                err_detail = f"Malformed JSON in A2A output block: {json_err}"
                logger.warning(err_detail)
                if publisher:
                    publisher.publish(
                        source_id=agent_id or "hermes_runner",
                        source_kind="runtime",
                        kind="conversation.invalid_a2a_output",
                        detail=err_detail,
                        job_id=job_id,
                        metadata={"raw_block": cleaned[:500], "error": str(json_err)},
                    )
                if strict:
                    raise ValueError(err_detail) from json_err
                continue

            items = parsed_json if isinstance(parsed_json, list) else [parsed_json]
            for item in items:
                if not isinstance(item, dict):
                    err_detail = f"A2A output item must be a JSON object, got {type(item).__name__}"
                    logger.warning(err_detail)
                    if publisher:
                        publisher.publish(
                            source_id=agent_id or "hermes_runner",
                            source_kind="runtime",
                            kind="conversation.invalid_a2a_output",
                            detail=err_detail,
                            job_id=job_id,
                            metadata={"item": str(item)[:500]},
                        )
                    if strict:
                        raise ValueError(err_detail)
                    continue

                try:
                    msg = A2AOutput.from_dict(item)
                    if not msg.to:
                        logger.warning("A2A output ignored: 'to' recipient list is empty")
                        if publisher:
                            publisher.publish(
                                source_id=agent_id or "hermes_runner",
                                source_kind="runtime",
                                kind="conversation.invalid_a2a_output",
                                detail="A2A output missing 'to' recipient list",
                                job_id=job_id,
                                metadata={"intent": msg.intent},
                            )
                        continue

                    if len(msg.text) > 50000:
                        msg.text = msg.text[:50000]

                    outgoing_messages.append(msg)
                except Exception as parse_err:
                    err_detail = f"Failed constructing A2AOutput from item: {parse_err}"
                    logger.warning(err_detail)
                    if publisher:
                        publisher.publish(
                            source_id=agent_id or "hermes_runner",
                            source_kind="runtime",
                            kind="conversation.invalid_a2a_output",
                            detail=err_detail,
                            job_id=job_id,
                            metadata={"error": str(parse_err)},
                        )
                    if strict:
                        raise

        # 2. Parse Delegation Blocks (Phase 7)
        try:
            from delegation import DelegationRequest, LYSSTACK_DELEGATION_START, LYSSTACK_DELEGATION_END
            del_pattern = re.compile(
                rf"{re.escape(LYSSTACK_DELEGATION_START)}\s*(.*?)\s*{re.escape(LYSSTACK_DELEGATION_END)}",
                re.DOTALL,
            )
            del_matches = del_pattern.findall(raw_text)
            for block in del_matches:
                cleaned = block.strip()
                if not cleaned:
                    continue
                try:
                    parsed_json = json.loads(cleaned)
                    items = parsed_json if isinstance(parsed_json, list) else [parsed_json]
                    for item in items:
                        if isinstance(item, dict):
                            req = DelegationRequest.from_dict(item)
                            if req.task and req.requiredCapabilities:
                                delegation_requests.append(req)
                except Exception as del_err:
                    logger.warning("Malformed JSON in delegation block: %s", del_err)
                    if publisher:
                        publisher.publish(
                            source_id=agent_id or "hermes_runner",
                            source_kind="runtime",
                            kind="delegation.rejected",
                            detail=f"Malformed JSON in delegation block: {del_err}",
                            job_id=job_id,
                            metadata={"raw_block": cleaned[:500]},
                        )
        except ImportError:
            pass

        # 3. Parse Tool Request Blocks (Phase 7)
        try:
            from tools import ToolInvocationRequest, LYSSTACK_TOOL_REQUEST_START, LYSSTACK_TOOL_REQUEST_END
            tool_pattern = re.compile(
                rf"{re.escape(LYSSTACK_TOOL_REQUEST_START)}\s*(.*?)\s*{re.escape(LYSSTACK_TOOL_REQUEST_END)}",
                re.DOTALL,
            )
            tool_matches = tool_pattern.findall(raw_text)
            for block in tool_matches:
                cleaned = block.strip()
                if not cleaned:
                    continue
                try:
                    parsed_json = json.loads(cleaned)
                    items = parsed_json if isinstance(parsed_json, list) else [parsed_json]
                    for item in items:
                        if isinstance(item, dict):
                            treq = ToolInvocationRequest.from_dict(item)
                            if treq.toolId:
                                tool_requests.append(treq)
                except Exception as tool_err:
                    logger.warning("Malformed JSON in tool request block: %s", tool_err)
                    if publisher:
                        publisher.publish(
                            source_id=agent_id or "hermes_runner",
                            source_kind="runtime",
                            kind="tool.rejected",
                            detail=f"Malformed JSON in tool request block: {tool_err}",
                            job_id=job_id,
                            metadata={"raw_block": cleaned[:500]},
                        )
        except ImportError:
            pass

        return AgentTurnResult(
            execution_result=execution_result,
            text=raw_text,
            outgoing_messages=outgoing_messages,
            delegation_requests=delegation_requests,
            tool_requests=tool_requests,
        )


def parse_a2a_output(
    raw_text: Any,
    execution_result: Any = None,
    strict: bool = False,
    publisher: Any = None,
    job_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> AgentTurnResult:
    """Convenience functional wrapper for A2AOutputParser."""
    return A2AOutputParser.parse(
        raw_text=raw_text,
        execution_result=execution_result,
        strict=strict,
        publisher=publisher,
        job_id=job_id,
        agent_id=agent_id,
    )


def validate_reply_to(
    reply_to: Optional[str],
    thread_id: str,
    conversation_id: Optional[str],
    known_messages: Sequence[Mapping[str, Any]],
    publisher: Any = None,
    job_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> bool:
    """
    Validates graph consistency of a replyTo reference:
    1. If reply_to is None or empty: valid (root message / historical).
    2. Referenced message must exist in known_messages.
    3. Referenced message must belong to the same threadId.
    4. Referenced message must belong to the same jobId (if jobId is set).
    5. Referenced message must belong to the same conversationId if conversationId is set.
    """
    if not reply_to:
        return True

    # Find referenced message
    target = next((m for m in known_messages if m.get("id") == reply_to), None)

    if not target:
        err_detail = f"Invalid replyTo: referenced message '{reply_to}' does not exist"
        logger.warning(err_detail)
        if publisher:
            publisher.publish(
                source_id=agent_id or "hermes_runner",
                source_kind="runtime",
                kind="conversation.invalid_reply",
                detail=err_detail,
                job_id=job_id,
                metadata={"replyTo": reply_to, "reason": "nonexistent_message"},
            )
        return False

    # Check thread match
    target_thread = target.get("threadId")
    if target_thread and target_thread != thread_id:
        err_detail = f"Invalid replyTo '{reply_to}': cross-thread reference (target thread: {target_thread}, current: {thread_id})"
        logger.warning(err_detail)
        if publisher:
            publisher.publish(
                source_id=agent_id or "hermes_runner",
                source_kind="runtime",
                kind="conversation.invalid_reply",
                detail=err_detail,
                job_id=job_id,
                metadata={"replyTo": reply_to, "targetThread": target_thread, "currentThread": thread_id},
            )
        return False

    # Check job match
    target_job = target.get("jobId")
    if job_id and target_job and target_job != job_id:
        err_detail = f"Invalid replyTo '{reply_to}': cross-job reference (target job: {target_job}, current: {job_id})"
        logger.warning(err_detail)
        if publisher:
            publisher.publish(
                source_id=agent_id or "hermes_runner",
                source_kind="runtime",
                kind="conversation.invalid_reply",
                detail=err_detail,
                job_id=job_id,
                metadata={"replyTo": reply_to, "targetJob": target_job, "currentJob": job_id},
            )
        return False

    # Check conversation match
    target_conv = target.get("conversationId")
    if conversation_id and target_conv and target_conv != conversation_id:
        err_detail = f"Invalid replyTo '{reply_to}': cross-conversation reference (target conv: {target_conv}, current: {conversation_id})"
        logger.warning(err_detail)
        if publisher:
            publisher.publish(
                source_id=agent_id or "hermes_runner",
                source_kind="runtime",
                kind="conversation.invalid_reply",
                detail=err_detail,
                job_id=job_id,
                metadata={"replyTo": reply_to, "targetConversation": target_conv, "currentConversation": conversation_id},
            )
        return False

    return True
