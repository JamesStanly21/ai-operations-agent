import unittest
import importlib
import os
from unittest.mock import patch

from app.agent.planner import AgentDecision

from app.agent.controller import AgentController
from app.approvals import store as approval_store
from app.approvals.service import (
    approve_proposal,
    create_proposal,
    reject_proposal,
)
from app.tools import reminders_tool, tasks_tool, tool_router
from app.workflows import store as workflow_store


class FixedPlanner:
    def __init__(self, actions):
        self.actions = actions

    def propose_plan(self, _objective, workspace_context=None):
        return {"actions": self.actions, "message": "Review the proposed actions."}


class SequencePlanner:
    def __init__(self, decisions):
        self.decisions = iter(decisions)

    def next_action(self, _instruction, _history, workspace_context=None):
        return next(self.decisions)


def task(title):
    return {"action": "create_task", "arguments": {"title": title}}


def reminder(title):
    return {"action": "create_reminder", "arguments": {
        "title": title, "reminder_time": "2026-10-12 09:00",
    }}


class ApprovalWorkflowIntegrationTests(unittest.TestCase):
    def setUp(self):
        tasks_tool.tasks.clear()
        reminders_tool.reminders.clear()
        approval_store.approval_requests.clear()
        workflow_store.workflows.clear()
        workflow_store.agent_runs.clear()
        workflow_store.workflow_steps.clear()
        self.original_tools = dict(tool_router.TOOLS)

    def tearDown(self):
        tool_router.TOOLS.clear()
        tool_router.TOOLS.update(self.original_tools)
        self.setUp()

    def proposal(self, actions, objective="Prepare the demo"):
        return create_proposal(objective, FixedPlanner(actions))

    def only_workflow(self):
        self.assertEqual(len(workflow_store.workflows), 1)
        workflow = next(iter(workflow_store.workflows.values()))
        self.assertEqual(len(workflow_store.agent_runs), 1)
        run = workflow_store.get_run(workflow.run_ids[0])
        return workflow, run, workflow_store.get_steps(run)

    def test_proposal_and_rejection_do_not_create_workflow_or_mutate_tools(self):
        approval = self.proposal([task("Slides")])
        self.assertEqual(workflow_store.workflows, {})
        rejected = reject_proposal(approval.id)
        self.assertEqual(rejected.status, "rejected")
        self.assertEqual(workflow_store.workflows, {})
        self.assertEqual(tasks_tool.tasks, [])

    def test_no_action_proposal_completes_without_workflow_or_run(self):
        approval = self.proposal([], objective="Everything is already ready")
        self.assertEqual(approval.status, "completed")
        self.assertIsNone(approval.workflow_id)
        self.assertIsNone(approval.run_id)
        self.assertEqual(workflow_store.workflows, {})
        self.assertEqual(workflow_store.agent_runs, {})

    def test_stale_proposal_does_not_create_workflow(self):
        approval = self.proposal([task("Slides")], "Make sure I have a task called Slides")
        tasks_tool.create_task("Slides")
        result = approve_proposal(approval.id, AgentController())
        self.assertEqual(result.status, "stale")
        self.assertIsNone(result.workflow_id)
        self.assertEqual(workflow_store.workflows, {})

    def test_approval_creates_provenance_and_one_step_per_action(self):
        approval = self.proposal([task("Slides"), reminder("Rehearse")])
        result = approve_proposal(approval.id, AgentController())

        workflow, run, steps = self.only_workflow()
        self.assertEqual(result.status, "completed")
        self.assertEqual((result.workflow_id, result.run_id), (workflow.id, run.id))
        self.assertEqual(workflow.source_approval_id, approval.id)
        self.assertEqual(workflow.status, "completed")
        self.assertEqual(run.status, "completed")
        self.assertEqual(len(steps), 2)
        for index, (step, action) in enumerate(zip(steps, approval.actions), start=1):
            self.assertEqual(step.order, index)
            self.assertEqual(step.action, action.action)
            self.assertEqual(step.arguments, action.arguments)
            self.assertEqual(step.status, "completed")
            self.assertEqual(step.approval_action_id, action.id)
            self.assertTrue(step.result["success"])
            self.assertTrue(step.resource_refs)
        self.assertEqual([step.resource_refs for step in steps], [["1"], ["1"]])

    def test_first_action_failure_marks_workflow_and_approval_failed(self):
        approval = self.proposal([task("Fail"), task("Skip")])
        tool_router.TOOLS["create_task"] = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
        result = approve_proposal(approval.id, AgentController())

        workflow, run, steps = self.only_workflow()
        self.assertEqual((result.status, workflow.status, run.status), ("failed", "failed", "failed"))
        self.assertEqual([step.status for step in steps], ["failed", "skipped"])
        self.assertIn("boom", steps[0].error)
        self.assertIn("earlier action failed", steps[1].error)
        self.assertIn("No approved actions completed", run.final_message)

    def test_later_failure_preserves_success_and_skips_remaining_actions(self):
        approval = self.proposal([task("First"), reminder("Fails"), task("Never")])
        tool_router.TOOLS["create_reminder"] = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("reminder boom"))
        result = approve_proposal(approval.id, AgentController())

        workflow, run, steps = self.only_workflow()
        self.assertEqual((result.status, workflow.status, run.status), (
            "partially_completed", "partially_completed", "partially_completed",
        ))
        self.assertEqual([step.status for step in steps], ["completed", "failed", "skipped"])
        self.assertEqual(steps[0].resource_refs, ["1"])
        self.assertIn("reminder boom", steps[1].error)
        self.assertIn("earlier action failed", steps[2].error)
        self.assertEqual([item["title"] for item in tasks_tool.tasks], ["First"])

    def test_stale_between_actions_is_recorded_and_not_dispatched(self):
        existing = tasks_tool.create_task("Existing")['task']
        approval = self.proposal([
            task("First"),
            {"action": "complete_task", "arguments": {"task_id": existing["id"]}},
            task("Never"),
        ])
        original_create = tool_router.TOOLS["create_task"]
        complete_calls = []

        def create_then_change(**kwargs):
            created = original_create(**kwargs)
            next(item for item in tasks_tool.tasks if item["id"] == existing["id"])["status"] = "completed"
            return created

        original_complete = tool_router.TOOLS["complete_task"]
        def count_complete(**kwargs):
            complete_calls.append(kwargs)
            return original_complete(**kwargs)

        tool_router.TOOLS["create_task"] = create_then_change
        tool_router.TOOLS["complete_task"] = count_complete
        result = approve_proposal(approval.id, AgentController())

        workflow, run, steps = self.only_workflow()
        self.assertEqual(result.status, "partially_completed")
        self.assertEqual(workflow.status, "partially_completed")
        self.assertEqual([step.status for step in steps], ["completed", "stale", "skipped"])
        self.assertEqual(complete_calls, [])
        self.assertEqual(steps[0].approval_action_id, approval.actions[0].id)
        self.assertEqual(steps[1].approval_action_id, approval.actions[1].id)
        self.assertIn("changed after", steps[1].error)

    def test_repeated_approval_does_not_create_a_second_workflow(self):
        approval = self.proposal([task("Once")])
        first = approve_proposal(approval.id, AgentController())
        second = approve_proposal(approval.id, AgentController())
        self.assertEqual(first.workflow_id, second.workflow_id)
        self.assertEqual(len(workflow_store.workflows), 1)
        self.assertEqual(len(tasks_tool.tasks), 1)
        self.assertEqual(len(workflow_store.workflow_steps), 1)

    def test_existing_agent_and_direct_workflow_routes_remain_compatible(self):
        # The app constructs its Groq planner at import time; use a harmless
        # local key and replace the planner before exercising either route.
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            main = importlib.import_module("app.main")
        from app.api.agent_api import AgentRequest, agent, run_agent
        from app.api.workflows_api import WorkflowRequest, create_workflow

        agent.planner = SequencePlanner([
            AgentDecision(action="create_task", title="Direct task"),
            AgentDecision(action="done", message="Task created."),
        ])
        self.assertIsNotNone(main.app)
        response = run_agent(AgentRequest(instruction="Create Direct task"))
        self.assertTrue(response["success"])
        self.assertEqual(response["steps"][0]["action"]["action"], "create_task")

        agent.planner = SequencePlanner([
            AgentDecision(action="create_task", title="Workflow task"),
            AgentDecision(action="done", message="Workflow task created."),
        ])
        workflow_response = create_workflow(WorkflowRequest(objective="Create Workflow task"))
        self.assertEqual(workflow_response["workflow"].status, "completed")
        self.assertEqual(workflow_response["steps"][0].action, "create_task")
        self.assertEqual(len(workflow_store.workflows), 1)


if __name__ == "__main__":
    unittest.main()
