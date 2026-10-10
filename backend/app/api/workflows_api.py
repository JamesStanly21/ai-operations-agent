from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.agent_api import agent
from app.workflows import store
from app.workflows.service import execute_workflow, get_workflow_detail


router = APIRouter(prefix="/workflows", tags=["Workflows"])


class WorkflowRequest(BaseModel):
    objective: str = Field(min_length=1)


@router.post("")
def create_workflow(request: WorkflowRequest) -> Dict[str, Any]:
    if not request.objective.strip():
        raise HTTPException(status_code=422, detail="Objective cannot be empty.")
    return execute_workflow(request.objective, agent)


@router.get("")
def read_workflows():
    return store.list_workflows()


@router.get("/{workflow_id}")
def read_workflow(workflow_id: str):
    workflow = store.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return get_workflow_detail(workflow)
