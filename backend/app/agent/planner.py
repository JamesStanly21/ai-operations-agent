import os
import json
from typing import Any, Dict, Literal, Optional

from groq import Groq
from pydantic import BaseModel, Field

from app.config import load_environment


load_environment()


class AgentDecision(BaseModel):
    action: Literal[
        "create_task",
        "get_tasks",
        "complete_task",
        "update_task",
        "create_reminder",
        "get_reminders",
        "done",
    ]

    title: Optional[str] = None
    description: Optional[str] = None
    task_id: Optional[int] = None
    reminder_time: Optional[str] = None
    message: Optional[str] = None


class AgentPlanner:

    def __init__(self):

        api_key = os.getenv("GROQ_API_KEY")

        if not api_key:
            raise ValueError("GROQ_API_KEY is not set.")

        self.client = Groq(api_key=api_key)

    def next_action(
        self,
        instruction: str,
        history: list,
        workspace_context: Optional[Dict[str, Any]] = None,
    ) -> AgentDecision:

        history_text = (
            "\n\nPrevious actions and observations:\n"
            + json.dumps(history, ensure_ascii=False, default=str)
            if history
            else ""
        )
        context_text = json.dumps(workspace_context or {}, ensure_ascii=False, default=str)

        prompt = f"""
You are the decision-making brain of an AI Operations Agent.

The user gave this objective:

{instruction}

Your job is to choose EXACTLY ONE next action.

Current workspace context (grounded in live backend state):
{context_text}

Available tools:

1. create_task
   - title: required
   - description: optional

2. get_tasks
   - no arguments

3. complete_task
   - task_id: required

4. update_task
   - task_id: required
   - title: optional
   - description: optional

5. create_reminder
   - title: required
   - reminder_time: required

6. get_reminders
   - no arguments

7. done
   - use when the objective has been completely accomplished

IMPORTANT RULES:

- Choose ONLY ONE action.
- DO NOT plan multiple future actions.
- Always observe the result of the current action before deciding the next action.
- Existing tasks, reminders, and workflows may already satisfy all or part of the objective.
- Treat completed matching work as already satisfied; do not recreate it.
- Reuse relevant pending work and create only what is missing and necessary.
- After each action, use the refreshed workspace context and observation to reassess the objective.
- If the objective is already satisfied, choose done and explain that no additional action is necessary.
- If required work cannot be completed, choose done and clearly explain what remains and why.
- NEVER invent a task ID.
- If you need a task ID but do not know it, use get_tasks first.
- Create a task when the user explicitly asks to create/add/make one, or
  when an ensure/prepare objective requires a task that is missing.
  NEVER create a task as a fallback for a completion request.
- If the user asks to complete an existing task by title or description and
  its ID is unknown, ALWAYS choose get_tasks first.
- After get_tasks returns the tasks, inspect them carefully:
  * Find tasks whose title matches what the user mentioned.
  * Among those matches, pick ONLY the FIRST task whose status is "pending".
  * Complete ONLY that single task ID, then immediately choose done.
  * If there is no matching pending task, choose done with a clear message
    that the requested task was not found. Do NOT create or complete any task.
  * NEVER complete more than one task in a session unless the user explicitly
    said "all", "every", "all matching", or "multiple".
- Once you have successfully completed ONE matching task, your job is done.
  Choose done immediately. Do NOT complete additional tasks with the same name.
- Never complete an already-completed task unless explicitly requested.
- For reminders, use YYYY-MM-DD HH:MM format.
- Today's date is 2026-10-10.
- If the objective is complete, choose done.
- Do not execute tools yourself.

Return ONLY valid JSON.

The JSON must have this structure:

{{
    "action": "one of the available actions",
    "title": null,
    "description": null,
    "task_id": null,
    "reminder_time": null,
    "message": null
}}

{history_text}
"""

        response = self.client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0,
            max_completion_tokens=1000,
            response_format={
                "type": "json_object"
            },
        )

        content = response.choices[0].message.content

        data = json.loads(content)

        return AgentDecision.model_validate(data)

    def propose_plan(
        self,
        instruction: str,
        workspace_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return a proposal only; this method never invokes workspace tools."""
        context_text = json.dumps(workspace_context or {}, ensure_ascii=False, default=str)
        prompt = f"""
You are planning operations for a human to review. Do not execute tools.

Objective:
{instruction}

Current workspace state:
{context_text}

Return a JSON object with:
- actions: ordered list of objects with action and arguments
- message: short explanation or no-action reason

Allowed actions:
- create_task: {{"title": string, "description": optional string}}
- complete_task: {{"task_id": integer}}
- update_task: {{"task_id": integer, "title": optional string, "description": optional string}}
- create_reminder: {{"title": string, "reminder_time": "YYYY-MM-DD HH:MM"}}
- create_calendar_event: {{"title": string, "start_time": ISO 8601 string, "end_time": ISO 8601 string, "description": optional string, "timezone": optional string, "location": optional string}}
- get_calendar_events: {{"start_time": optional ISO 8601 string, "end_time": optional ISO 8601 string}}
- update_calendar_event: {{"event_id": string, at least one of title/start_time/end_time/description/timezone/location}}
- cancel_calendar_event: {{"event_id": string}}
- draft_email: {{"to": email address or list, "subject": string, "body": string, "cc": optional email address or list}}
- send_email: {{"to": email address or list, "subject": string, "body": string, "cc": optional email address or list}}

Only propose actions necessary for the objective. Reuse relevant pending work,
do not recreate completed work, and do not propose duplicate task titles for
ensure/prepare/check objectives. If the objective is already satisfied, return
an empty actions list. A calendar read may be proposed when needed to ground
an external action. Never propose unsupported actions or actions whose required identifiers are absent. External side effects such as
calendar creation/updates/cancellation, email drafting, and email sending are
executed only after human approval. The backend validates your plan.

Return only valid JSON in this shape:
{{"actions": [{{"action": "create_task", "arguments": {{"title": "..."}}}}], "message": "..."}}
"""
        response = self.client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_completion_tokens=2000,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        proposal = json.loads(content)
        if not isinstance(proposal, dict):
            raise ValueError("Planner returned an invalid proposal.")
        return proposal
