from typing import Dict, List, Optional
from uuid import uuid4

from app.workflows.models import AgentRun, Workflow, WorkflowStep, utc_now


workflows: Dict[str, Workflow] = {}
agent_runs: Dict[str, AgentRun] = {}
workflow_steps: Dict[str, WorkflowStep] = {}


def create_workflow(
    title: str,
    objective: str,
    source_approval_id: Optional[str] = None,
) -> Workflow:
    workflow = Workflow(
        id=str(uuid4()),
        title=title,
        objective=objective,
        source_approval_id=source_approval_id,
    )
    workflows[workflow.id] = workflow
    return workflow


def create_run(workflow: Workflow) -> AgentRun:
    run = AgentRun(id=str(uuid4()), workflow_id=workflow.id)
    agent_runs[run.id] = run
    workflow.active_run_id = run.id
    workflow.run_ids.append(run.id)
    workflow.updated_at = utc_now()
    return run


def add_step(step: WorkflowStep) -> None:
    workflow_steps[step.id] = step
    run = agent_runs[step.run_id]
    run.step_ids.append(step.id)


def get_workflow(workflow_id: str) -> Optional[Workflow]:
    return workflows.get(workflow_id)


def list_workflows() -> List[Workflow]:
    return sorted(workflows.values(), key=lambda item: item.created_at, reverse=True)


def get_run(run_id: str) -> Optional[AgentRun]:
    return agent_runs.get(run_id)


def get_steps(run: AgentRun) -> List[WorkflowStep]:
    return [workflow_steps[step_id] for step_id in run.step_ids]
