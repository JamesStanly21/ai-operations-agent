from typing import Any, Dict, List

from app.integrations.base import operation_result


class MockEmailAdapter:
    provider_name = "mock-email"
    execution_mode = "simulated"

    def __init__(self):
        self.drafts: List[Dict[str, Any]] = []
        self.sent_messages: List[Dict[str, Any]] = []

    def draft_email(self, **arguments: Any) -> Dict[str, Any]:
        draft = {"id": f"draft-{len(self.drafts) + 1}", **arguments, "status": "draft"}
        self.drafts.append(draft)
        return operation_result(self, success=True, message="Email draft created (simulated).", draft=draft)

    def send_email(self, **arguments: Any) -> Dict[str, Any]:
        email = {"id": f"email-{len(self.sent_messages) + 1}", **arguments, "status": "sent"}
        self.sent_messages.append(email)
        return operation_result(self, success=True, message="Email sent (simulated).", email=email)
