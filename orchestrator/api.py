"""HTTP routes for the orchestrator chat. Chat and draft only: there is no run route here."""

import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from orchestrator.chat import (
    CLAUDE_MODELS,
    EFFORT_LEVELS,
    ChatError,
    ClaudeChatProvider,
    ConversationStore,
    OrchestratorChat,
    default_state_dir,
)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


def default_lysstack_root():
    return Path(os.environ.get("HERMES_LYSSTACK_ROOT", Path.home() / "Projects" / "LysStack"))


def tools_config(root):
    repo = Path(__file__).resolve().parent.parent
    return {"python": sys.executable, "repo": repo, "root": root, "drafts": root / "drafts",
            "state": default_state_dir()}


def get_chat():
    return OrchestratorChat(
        store=ConversationStore(default_state_dir()),
        provider=ClaudeChatProvider(tools=tools_config(default_lysstack_root())),
        lysstack_root=default_lysstack_root(),
    )


class NewConversation(BaseModel):
    model: str = "claude-sonnet-5-5"
    effort: str | None = None
    title: str | None = Field(default=None, max_length=120)


class NewMessage(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


def _fail(exc):
    raise HTTPException(status_code=400, detail=str(exc))


@router.get("/options")
def options():
    return {"providers": [{"id": "claude", "models": list(CLAUDE_MODELS), "efforts": list(EFFORT_LEVELS)}]}


@router.get("/conversations")
def list_conversations():
    return get_chat().store.list()


@router.post("/conversations", status_code=201)
def create_conversation(body: NewConversation):
    try:
        return get_chat().start(body.model, body.effort, body.title)
    except ChatError as exc:
        _fail(exc)


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    try:
        return get_chat().store.get(conversation_id)
    except ChatError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


class UpdateConversation(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    model: str | None = None
    effort: str | None = None


@router.patch("/conversations/{conversation_id}")
def update_conversation(conversation_id: str, body: UpdateConversation):
    try:
        return get_chat().update(
            conversation_id,
            title=body.title,
            model=body.model,
            effort=body.effort,
            effort_given="effort" in body.model_fields_set,
        )
    except ChatError as exc:
        if str(exc) == "unknown conversation":
            raise HTTPException(status_code=404, detail=str(exc))
        _fail(exc)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str):
    try:
        get_chat().delete(conversation_id)
    except ChatError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return Response(status_code=204)


@router.post("/conversations/{conversation_id}/compact")
def compact_conversation(conversation_id: str):
    try:
        return get_chat().compact(conversation_id)
    except ChatError as exc:
        if str(exc) == "unknown conversation":
            raise HTTPException(status_code=404, detail=str(exc))
        _fail(exc)


@router.post("/conversations/{conversation_id}/messages", status_code=201)
def send_message(conversation_id: str, body: NewMessage):
    try:
        return get_chat().send(conversation_id, body.content)
    except ChatError as exc:
        _fail(exc)
