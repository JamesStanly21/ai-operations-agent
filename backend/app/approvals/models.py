from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


ApprovalStatus = Literal[
    "pending_approval",
    "approved",
    "executing",
    "completed",
    "partially_completed",
    "failed",
    "rejected",
    "stale",
]

ActionStatus = Literal["pending", "completed", "failed", "skipped", "stale"]
ActionName = Literal[
    "create_task", "complete_task", "update_task", "create_reminder",
    "create_calendar_event", "get_calendar_events", "update_calendar_event",
    "cancel_calendar_event", "draft_email", "send_email",
]


class ProposedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    order: int = Field(ge=1)
    action: ActionName
    arguments: Dict[str, Any] = Field(default_factory=dict)
    status: ActionStatus = "pending"
    preconditions: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    resource_refs: List[str] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    objective: str
    status: ApprovalStatus = "pending_approval"
    revision: int = Field(default=1, ge=1)
    actions: List[ProposedAction] = Field(default_factory=list)
    workflow_id: Optional[str] = None
    run_id: Optional[str] = None
    message: Optional[str] = None
    rejection_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    approved_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
