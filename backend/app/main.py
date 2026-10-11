from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import load_environment


load_environment()

from app.api.agent_api import router as agent_router
from app.api.workflows_api import router as workflows_router
from app.api.approvals_api import router as approvals_router
from app.api.google_calendar_api import router as google_calendar_router
from app.tools.tasks_tool import get_tasks, complete_task
from app.tools.reminders_tool import get_reminders


app = FastAPI(
    title="AI Operations Agent",
    description="AI-powered operations agent",
    version="0.1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://ai-operations-agent-frontend.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(agent_router)
app.include_router(workflows_router)
app.include_router(approvals_router)
app.include_router(google_calendar_router)


@app.get("/tasks")
def read_tasks():
    return get_tasks()


@app.get("/reminders")
def read_reminders():
    return get_reminders()


@app.post("/tasks/{task_id}/complete")
def mark_task_complete(task_id: int):
    result = complete_task(task_id)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/")
def root():
    return {
        "message": "AI Operations Agent is running",
        "status": "ok",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}
