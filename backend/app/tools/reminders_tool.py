from typing import Dict


reminders = []


def create_reminder(title: str, reminder_time: str) -> Dict:
    reminder = {
        "id": len(reminders) + 1,
        "title": title,
        "reminder_time": reminder_time,
        "status": "scheduled",
    }

    reminders.append(reminder)

    return {
        "success": True,
        "message": f"Reminder '{title}' scheduled successfully.",
        "reminder": reminder,
    }


def get_reminders() -> Dict:
    return {
        "success": True,
        "reminders": reminders,
    }