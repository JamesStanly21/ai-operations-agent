import unittest

from app.agent.agent import OperationsAgent
from app.agent.planner import AgentDecision
from app.tools import reminders_tool, tasks_tool
from app.workflows import store
from app.workflows.service import execute_workflow


class SequencePlanner:
    def __init__(self, decisions, inspect=None):
        self.decisions = iter(decisions)
        self.contexts = []
        self.histories = []
        self.inspect = inspect

    def next_action(self, instruction, history, workspace_context=None):
        self.contexts.append(workspace_context)
        self.histories.append(list(history))
        if self.inspect:
            self.inspect(instruction, history, workspace_context)
        return next(self.decisions)


class FailingController:
    def execute_plan(self, plan):
        return {"results": [{"result": {
            "success": False,
            "tool": plan[0]["tool"],
            "error": "simulated tool failure",
        }}]}


def decision(action, title=None, task_id=None, message=None):
    return AgentDecision(
        action=action,
        title=title,
        task_id=task_id,
        message=message,
    )


def agent_with(planner, controller=None):
    agent = OperationsAgent.__new__(OperationsAgent)
    agent.planner = planner
    agent.controller = controller
    if controller is None:
        from app.agent.controller import AgentController
        agent.controller = AgentController()
    return agent


class WorkspaceContextTests(unittest.TestCase):
    def setUp(self):
        tasks_tool.tasks.clear()
        reminders_tool.reminders.clear()
        store.workflows.clear()
        store.agent_runs.clear()
        store.workflow_steps.clear()

    def tearDown(self):
        self.setUp()

    def test_existing_exact_title_is_not_duplicated(self):
        tasks_tool.create_task("Prepare hackathon slides")
        planner = SequencePlanner([
            decision("create_task", "Prepare hackathon slides"),
            decision("done", message="The task already exists."),
        ])
        result = agent_with(planner).run(
            "Make sure I have a task to prepare hackathon slides"
        )

        self.assertTrue(result["success"])
        self.assertEqual(len(tasks_tool.tasks), 1)
        self.assertTrue(planner.histories[1][0]["observation"]["result"]["already_exists"])
        self.assertEqual(planner.contexts[1]["tasks"][0]["title"], "Prepare hackathon slides")

    def test_missing_task_can_be_created_and_context_refreshes(self):
        planner = SequencePlanner([
            decision("create_task", "Prepare demo"),
            decision("done", message="The task is ready."),
        ])
        result = agent_with(planner).run("Make sure I have a task to prepare demo")

        self.assertTrue(result["success"])
        self.assertEqual([task["title"] for task in tasks_tool.tasks], ["Prepare demo"])
        self.assertEqual(planner.contexts[0]["tasks"], [])
        self.assertEqual(planner.contexts[1]["tasks"][0]["title"], "Prepare demo")

    def test_mixed_state_creates_only_missing_task(self):
        tasks_tool.create_task("Prepare outline")
        planner = SequencePlanner([
            decision("create_task", "Prepare demo"),
            decision("done", message="Existing outline reused; demo task added."),
        ])
        agent_with(planner).run("Prepare outline and demo")

        self.assertEqual(
            [task["title"] for task in tasks_tool.tasks],
            ["Prepare outline", "Prepare demo"],
        )
        self.assertEqual(len(planner.contexts[0]["tasks"]), 1)

    def test_already_satisfied_objective_needs_no_action(self):
        tasks_tool.create_task("Prepare demo")
        planner = SequencePlanner([
            decision("done", message="The existing task already satisfies this objective; no additional action is necessary.")
        ])
        result = agent_with(planner).run("Check that I have a task to prepare demo")

        self.assertEqual(result["steps"], [])
        self.assertIn("no additional action", result["final_message"])
        self.assertEqual(len(tasks_tool.tasks), 1)

    def test_explicit_another_task_request_is_not_blocked(self):
        tasks_tool.create_task("Prepare demo")
        planner = SequencePlanner([
            decision("create_task", "Prepare demo"),
            decision("done", message="Another task was created."),
        ])
        agent_with(planner).run("Create another task called Prepare demo")

        self.assertEqual(len(tasks_tool.tasks), 2)

    def test_failure_is_visible_to_next_decision_and_workflow(self):
        def check_failure(_instruction, history, _context):
            if history:
                self.assertTrue(any(item.get("type") == "tool_failure" for item in history))

        planner = SequencePlanner([
            decision("create_task", "Failing task"),
            decision("done", message="Could not create the task after a tool failure."),
        ], inspect=check_failure)
        agent = agent_with(planner, FailingController())
        result = execute_workflow("Create a failing task", agent)

        self.assertEqual(result["workflow"].status, "failed")
        self.assertEqual(result["steps"][0].status, "failed")
        self.assertIn("simulated tool failure", planner.histories[1][1]["message"])
        self.assertEqual(planner.contexts[0]["workflows"], [])
        current_workflow = planner.contexts[1]["workflows"][0]
        self.assertEqual(current_workflow["steps"][0]["status"], "failed")
        self.assertIn("simulated tool failure", current_workflow["failures"][0]["error"])

    def test_duplicate_completion_still_completes_only_first_pending(self):
        first = tasks_tool.create_task("Prepare demo")["task"]
        second = tasks_tool.create_task("Prepare demo")["task"]
        planner = SequencePlanner([
            decision("get_tasks"),
            decision("complete_task", task_id=first["id"]),
            decision("done", message="Completed the first pending match."),
        ])
        agent_with(planner).run("Check my tasks and complete the task called Prepare demo")

        self.assertEqual(tasks_tool.tasks[0]["status"], "completed")
        self.assertEqual(tasks_tool.tasks[1]["id"], second["id"])
        self.assertEqual(tasks_tool.tasks[1]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
