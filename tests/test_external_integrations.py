import unittest

from app.agent.controller import AgentController
from app.approvals import store as approval_store
from app.approvals.service import (
    InvalidProposal,
    approve_proposal,
    create_proposal,
    reject_proposal,
)
from app.integrations.calendar.mock import MockCalendarAdapter
from app.integrations.email.mock import MockEmailAdapter
from app.integrations import registry
from app.tools import reminders_tool, tasks_tool, tool_router
from app.workflows import store as workflow_store


class DeterministicPlanner:
    def __init__(self, actions):
        self.actions = actions

    def propose_plan(self, _objective, workspace_context=None):
        return {"actions": self.actions, "message": "Review the external actions."}


def action(name, **arguments):
    return {"action": name, "arguments": arguments}


def event_action(title="Hackathon presentation"):
    return action(
        "create_calendar_event",
        title=title,
        start_time="2026-10-12T09:00:00+05:30",
        end_time="2026-10-12T10:00:00+05:30",
        location="Conference room",
    )


def email_action(tool="send_email", subject="Demo details"):
    return action(
        tool,
        to="teammate@example.com",
        subject=subject,
        body="The demo starts at 9 AM.",
    )


class FailingEmailAdapter(MockEmailAdapter):
    def send_email(self, **_arguments):
        raise RuntimeError("simulated provider outage")


class ExternalIntegrationTests(unittest.TestCase):
    def setUp(self):
        tasks_tool.tasks.clear()
        reminders_tool.reminders.clear()
        approval_store.approval_requests.clear()
        workflow_store.workflows.clear()
        workflow_store.agent_runs.clear()
        workflow_store.workflow_steps.clear()
        registry.set_calendar_adapter(MockCalendarAdapter())
        registry.set_email_adapter(MockEmailAdapter())
        self.original_tools = dict(tool_router.TOOLS)

    def tearDown(self):
        tool_router.TOOLS.clear()
        tool_router.TOOLS.update(self.original_tools)
        self.setUp()

    def propose(self, actions):
        return create_proposal("Prepare the hackathon demo", DeterministicPlanner(actions))

    def workflow_for(self, approval):
        workflow = workflow_store.get_workflow(approval.workflow_id)
        run = workflow_store.get_run(approval.run_id)
        return workflow, run, workflow_store.get_steps(run)

    def test_email_draft_executes_as_simulated_approved_tool(self):
        approval = self.propose([email_action("draft_email")])
        result = approve_proposal(approval.id, AgentController())

        email_adapter = registry.get_email_adapter()
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(email_adapter.drafts), 1)
        self.assertEqual(email_adapter.sent_messages, [])
        workflow, _run, steps = self.workflow_for(result)
        self.assertEqual(workflow.source_approval_id, approval.id)
        self.assertEqual(steps[0].action, "draft_email")
        self.assertEqual(steps[0].resource_refs, ["draft-1"])
        self.assertEqual(steps[0].result["result"]["execution_mode"], "simulated")

    def test_email_send_executes_exactly_once_after_approval(self):
        approval = self.propose([email_action()])
        first = approve_proposal(approval.id, AgentController())
        second = approve_proposal(approval.id, AgentController())

        self.assertEqual(first.status, "completed")
        self.assertEqual(second.workflow_id, first.workflow_id)
        self.assertEqual(len(registry.get_email_adapter().sent_messages), 1)
        workflow, run, steps = self.workflow_for(first)
        self.assertEqual((workflow.status, run.status), ("completed", "completed"))
        self.assertEqual(steps[0].action, "send_email")
        self.assertEqual(steps[0].approval_action_id, approval.actions[0].id)
        self.assertEqual(steps[0].resource_refs, ["email-1"])

    def test_calendar_event_create_and_read_are_simulated_and_recorded(self):
        approval = self.propose([event_action()])
        result = approve_proposal(approval.id, AgentController())

        self.assertEqual(result.status, "completed")
        self.assertEqual(len(registry.get_calendar_adapter().events), 1)
        workflow, _run, steps = self.workflow_for(result)
        self.assertEqual(steps[0].action, "create_calendar_event")
        self.assertEqual(steps[0].resource_refs, ["event-1"])
        self.assertEqual(steps[0].result["result"]["provider"], "mock-calendar")
        read_result = AgentController().execute_plan([{
            "tool": "get_calendar_events",
            "arguments": {"start_time": "2026-10-12T00:00:00+05:30"},
        }])["results"][0]["result"]
        self.assertTrue(read_result["success"])
        self.assertEqual(read_result["result"]["events"][0]["id"], "event-1")

    def test_side_effecting_external_tools_require_approval(self):
        for tool, args in (
            ("send_email", email_action()["arguments"]),
            ("create_calendar_event", event_action()["arguments"]),
        ):
            result = tool_router.execute_tool(tool, args)
            self.assertFalse(result["success"])
            self.assertIn("requires an executing approved proposal", result["error"])
        self.assertEqual(registry.get_email_adapter().sent_messages, [])
        self.assertEqual(registry.get_calendar_adapter().events, [])

    def test_rejected_email_and_calendar_proposals_do_not_execute(self):
        email_approval = self.propose([email_action()])
        calendar_approval = self.propose([event_action()])
        reject_proposal(email_approval.id, "Do not send")
        reject_proposal(calendar_approval.id, "Do not schedule")

        self.assertEqual(registry.get_email_adapter().sent_messages, [])
        self.assertEqual(registry.get_calendar_adapter().events, [])
        self.assertEqual(workflow_store.workflows, {})

    def test_provider_failure_before_work_marks_failed_and_later_failure_partial(self):
        approval = self.propose([email_action()])
        registry.set_email_adapter(FailingEmailAdapter())
        result = approve_proposal(approval.id, AgentController())
        workflow, run, steps = self.workflow_for(result)
        self.assertEqual((result.status, workflow.status, run.status), ("failed", "failed", "failed"))
        self.assertEqual(steps[0].status, "failed")
        self.assertIn("simulated provider outage", steps[0].error)

        self.setUp()
        approval = self.propose([event_action(), email_action()])
        registry.set_email_adapter(FailingEmailAdapter())
        result = approve_proposal(approval.id, AgentController())
        workflow, run, steps = self.workflow_for(result)
        self.assertEqual((result.status, workflow.status, run.status), (
            "partially_completed", "partially_completed", "partially_completed",
        ))
        self.assertEqual([step.status for step in steps], ["completed", "failed"])
        self.assertEqual(steps[0].resource_refs, ["event-1"])
        self.assertIn("simulated provider outage", steps[1].error)

    def test_external_action_arguments_are_validated_before_approval(self):
        with self.assertRaises(InvalidProposal):
            self.propose([action("send_email", to="not-an-email", subject="x", body="y")])
        with self.assertRaises(InvalidProposal):
            self.propose([action(
                "create_calendar_event",
                title="Bad interval",
                start_time="2026-10-12T10:00:00",
                end_time="2026-10-12T09:00:00",
            )])


if __name__ == "__main__":
    unittest.main()
