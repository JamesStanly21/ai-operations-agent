from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent.controller import AgentController
from app.api.agent_api import agent
from app.approvals.service import (
    ApprovalServiceError,
    approve_proposal,
    create_proposal,
    edit_proposal,
    get_proposal,
    list_proposals,
    reject_proposal,
)


router = APIRouter(prefix="/approvals", tags=["Approvals"])


class ApprovalRequestBody(BaseModel):
    objective: str = Field(min_length=1)


class ApprovalEditBody(BaseModel):
    actions: list[Dict[str, Any]]


class ApprovalRejectBody(BaseModel):
    reason: Optional[str] = None


def _call(operation, *args):
    try:
        return operation(*args)
    except ApprovalServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("")
def create_approval(request: ApprovalRequestBody):
    if not request.objective.strip():
        raise HTTPException(status_code=422, detail="Objective cannot be empty.")
    return _call(create_proposal, request.objective, agent.planner)


@router.get("")
def read_approvals():
    return list_proposals()


@router.get("/{approval_id}")
def read_approval(approval_id: str):
    return _call(get_proposal, approval_id)


@router.patch("/{approval_id}")
def patch_approval(approval_id: str, request: ApprovalEditBody):
    return _call(edit_proposal, approval_id, request.actions)


@router.post("/{approval_id}/approve")
def approve_approval(approval_id: str):
    return _call(approve_proposal, approval_id, agent.controller)


@router.post("/{approval_id}/reject")
def reject_approval(approval_id: str, request: ApprovalRejectBody):
    return _call(reject_proposal, approval_id, request.reason)
