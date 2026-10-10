import unittest

from app.agent.controller import AgentController
from app.approvals import store
from app.approvals.service import (
    InvalidProposal,
    approve_proposal,
    create_proposal,
    edit_proposal,
    reject_proposal,
)
from app.tools import reminders_tool, tasks_tool, tool_router


class DeterministicPlanner:
    def __init__(self, actions, message="Review these proposed actions."):
        self.actions = actions
        self.message = message
        self.received_context = None

    def propose_plan(self, instruction, workspace_context=None):
        self.received_context = workspace_context
        return {"actions": self.actions, "message": self.message}


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        tasks_tool.tasks.clear()
        reminders_tool.reminders.clear()
        store.approval_requests.clear()
        self.original_reminder_tool = tool_router.TOOLS["create_reminder"]

    def tearDown(self):
        tool_router.TOOLS["create_reminder"] = self.original_reminder_tool
        tasks_tool.tasks.clear()
        reminders_tool.reminders.clear()
        store.approval_requests.clear()

    def test_proposal_creation_uses_context_and_performs_no_mutations(self):
        planner = DeterministicPlanner([
            {"action": "create_task", "arguments": {"title": "Prepare slides"}},
            {"action": "create_reminder", "arguments": {
                "title": "Rehearse", "reminder_time": "2026-10-12 09:00",
            }},
        ])
        approval = create_proposal("Prepare my presentation", planner)

        self.assertEqual(approval.status, "pending_approval")
        self.assertEqual(approval.revision, 1)
        self.assertEqual(len(approval.actions), 2)
        self.assertEqual(planner.received_context["tasks"], [])
        self.assertEqual(tasks_tool.tasks, [])
        self.assertEqual(reminders_tool.reminders, [])

    def test_malformed_action_is_rejected(self):
        planner = DeterministicPlanner([
            {"action": "delete_everything", "arguments": {}},
        ])
        with self.assertRaises(InvalidProposal):
            create_proposal("Do work", planner)
        self.assertEqual(tasks_tool.tasks, [])

    def test_edit_creates_new_pending_revision_without_execution(self):
        approval = create_proposal(
            "Create a task",
            DeterministicPlanner([{"action": "create_task", "arguments": {"title": "Old title"}}]),
        )
        edited = edit_proposal(approval.id, [
            {"action": "create_task", "arguments": {"title": "New title"}},
        ])

        self.assertEqual(edited.revision, 2)
        self.assertEqual(edited.status, "pending_approval")
        self.assertEqual(edited.actions[0].arguments["title"], "New title")
        self.assertEqual(tasks_tool.tasks, [])

    def test_reject_performs_no_mutations(self):
        approval = create_proposal(
            "Create a task",
            DeterministicPlanner([{"action": "create_task", "arguments": {"title": "Rejected"}}]),
        )
        rejected = reject_proposal(approval.id, "Not needed")

        self.assertEqual(rejected.status, "rejected")
        self.assertEqual(rejected.rejection_reason, "Not needed")
        self.assertEqual(tasks_tool.tasks, [])

    def test_stale_task_creation_is_rejected_before_any_execution(self):
        approval = create_proposal(
            "Make sure I have a task to prepare demo",
            DeterministicPlanner([{"action": "create_task", "arguments": {"title": "Prepare demo"}}]),
        )
        tasks_tool.create_task("Prepare demo")

        result = approve_proposal(approval.id, AgentController())

        self.assertEqual(result.status, "stale")
        self.assertEqual(len(tasks_tool.tasks), 1)
        self.assertEqual(result.actions[0].status, "pending")

    def test_stale_completion_is_rejected_before_execution(self):
        task = tasks_tool.create_task("Prepare demo")["task"]
        approval = create_proposal(
            "Complete Prepare demo",
            DeterministicPlanner([{"action": "complete_task", "arguments": {"task_id": task["id"]}}]),
        )
        tasks_tool.complete_task(task["id"])

        result = approve_proposal(approval.id, AgentController())

        self.assertEqual(result.status, "stale")
        self.assertEqual(tasks_tool.tasks[0]["status"], "completed")
        self.assertEqual(result.actions[0].status, "pending")

    def test_approval_executes_only_approved_actions_through_controller(self):
        approval = create_proposal(
            "Prepare slides and schedule rehearsal",
            DeterministicPlanner([
                {"action": "create_task", "arguments": {"title": "Prepare slides"}},
                {"action": "create_reminder", "arguments": {
                    "title": "Rehearse", "reminder_time": "2026-10-12 09:00",
                }},
            ]),
        )

        result = approve_proposal(approval.id, AgentController())

        self.assertEqual(result.status, "completed")
        self.assertEqual([item["title"] for item in tasks_tool.tasks], ["Prepare slides"])
        self.assertEqual([item["title"] for item in reminders_tool.reminders], ["Rehearse"])
        self.assertTrue(all(action.status == "completed" for action in result.actions))
        self.assertEqual(result.actions[0].resource_refs, ["1"])
        self.assertEqual(result.actions[1].resource_refs, ["1"])

    def test_repeated_approval_does_not_execute_twice(self):
        approval = create_proposal(
            "Create one task",
            DeterministicPlanner([{"action": "create_task", "arguments": {"title": "One task"}}]),
        )
        first = approve_proposal(approval.id, AgentController())
        second = approve_proposal(approval.id, AgentController())

        self.assertEqual(first.status, "completed")
        self.assertEqual(second.status, "completed")
        self.assertEqual(len(tasks_tool.tasks), 1)

    def test_partial_execution_records_success_failure_and_skipped_actions(self):
        approval = create_proposal(
            "Create task, reminder, and follow-up task",
            DeterministicPlanner([
                {"action": "create_task", "arguments": {"title": "First task"}},
                {"action": "create_reminder", "arguments": {
                    "title": "Failing reminder", "reminder_time": "2026-10-12 09:00",
                }},
                {"action": "create_task", "arguments": {"title": "Not reached"}},
            ]),
        )

        def fail_reminder(**_kwargs):
            raise RuntimeError("simulated reminder failure")

        tool_router.TOOLS["create_reminder"] = fail_reminder
        result = approve_proposal(approval.id, AgentController())

        self.assertEqual(result.status, "partially_completed")
        self.assertEqual([action.status for action in result.actions], ["completed", "failed", "skipped"])
        self.assertIn("simulated reminder failure", result.actions[1].error)
        self.assertEqual([task["title"] for task in tasks_tool.tasks], ["First task"])
        self.assertEqual(reminders_tool.reminders, [])


if __name__ == "__main__":
    unittest.main()
