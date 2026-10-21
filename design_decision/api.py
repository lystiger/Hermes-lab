"""Endpoints for the Unigreen design choice. Reads the current decision; records one, as a human decision."""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from design_decision.decision import DecisionError, current_decision, load_directions, record_decision

router = APIRouter(prefix="/design/unigreen", tags=["design"])
REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "console" / "public" / "design" / "unigreen" / "manifest.json"


def lysstack_root():
    return Path(os.environ.get("HERMES_LYSSTACK_ROOT", Path.home() / "Projects" / "LysStack"))


def decisions_file():
    return lysstack_root() / "projects" / "unigreen" / "decisions.md"


class DesignChoice(BaseModel):
    direction: str = Field(min_length=1, max_length=60)
    reason: str = Field(min_length=10, max_length=2000)


@router.get("/decision")
def get_decision():
    if not MANIFEST.is_file():
        raise HTTPException(status_code=404, detail="design manifest not found")
    return {"decision": current_decision(decisions_file()),
            "directions": [{"id": k, "label": v} for k, v in load_directions(MANIFEST).items()]}


@router.post("/decision", status_code=201)
def post_decision(choice: DesignChoice):
    if not MANIFEST.is_file():
        raise HTTPException(status_code=404, detail="design manifest not found")
    try:
        return record_decision(decisions_file(), MANIFEST, choice.direction, choice.reason)
    except DecisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
