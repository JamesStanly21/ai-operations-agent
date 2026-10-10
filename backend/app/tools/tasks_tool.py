from typing import Dict


tasks = []


def create_task(title: str, description: str = "") -> Dict:
    task = {
        "id": len(tasks) + 1,
        "title": title,
        "description": description,
        "status": "pending",
    }

    tasks.append(task)

    return {
        "success": True,
        "message": f"Task '{title}' created successfully.",
        "task": task,
    }


def get_tasks() -> Dict:
    return {
        "success": True,
        "tasks": tasks,
    }


def complete_task(task_id: int) -> Dict:
    for task in tasks:
        if task["id"] == task_id:

            if task["status"] == "completed":
                return {
                    "success": False,
                    "error": f"Task {task_id} is already completed.",
                    "task": task,
                }

            task["status"] = "completed"

            return {
                "success": True,
                "message": f"Task {task_id} completed successfully.",
                "task": task,
            }

    return {
        "success": False,
        "error": f"Task {task_id} not found.",
    }

def update_task(
    task_id: int,
    title: str = None,
    description: str = None,
) -> Dict:
    for task in tasks:
        if task["id"] == task_id:

            if title is not None:
                task["title"] = title

            if description is not None:
                task["description"] = description

            return {
                "success": True,
                "message": f"Task {task_id} updated successfully.",
                "task": task,
            }

    return {
        "success": False,
        "error": f"Task {task_id} not found.",
    }