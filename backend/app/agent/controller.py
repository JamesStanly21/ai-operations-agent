from typing import Any, Dict, List

from app.tools.tool_router import execute_tool


class AgentController:

    def execute_plan(self, plan: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = []

        for step in plan:
            tool_name = step["tool"]
            arguments = step.get("arguments", {})

            result = execute_tool(
                tool_name,
                arguments,
                approval_id=step.get("approval_id"),
                approval_action_id=step.get("approval_action_id"),
            )

            results.append({
                "step": step,
                "result": result,
            })

        return {
            "success": True,
            "steps_executed": len(results),
            "results": results,
        }
