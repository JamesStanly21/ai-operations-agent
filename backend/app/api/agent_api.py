from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel

from app.agent.agent import OperationsAgent


router = APIRouter(prefix="/agent", tags=["Agent"])

agent = OperationsAgent()


class AgentRequest(BaseModel):
    instruction: str


@router.post("/run")
def run_agent(request: AgentRequest) -> Dict[str, Any]:
    return agent.run(request.instruction)