from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowStep(BaseModel):
    id: str
    workflow_id: str
    run_id: str
    order: int
    title: str
    action: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    status: str = "running"
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: Optional[datetime] = None
    result: Any = None
    error: Optional[str] = None
    resource_refs: List[str] = Field(default_factory=list)
    approval_action_id: Optional[str] = None


class AgentRun(BaseModel):
    id: str
    workflow_id: str
    status: str = "running"
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: Optional[datetime] = None
    final_message: Optional[str] = None
    step_ids: List[str] = Field(default_factory=list)


class Workflow(BaseModel):
    id: str
    title: str
    objective: str
    status: str = "running"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    active_run_id: Optional[str] = None
    run_ids: List[str] = Field(default_factory=list)
    source_approval_id: Optional[str] = None
