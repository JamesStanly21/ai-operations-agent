from typing import Dict, List, Optional
from uuid import uuid4

from app.approvals.models import ApprovalRequest


approval_requests: Dict[str, ApprovalRequest] = {}


def create(approval: ApprovalRequest) -> ApprovalRequest:
    approval_requests[approval.id] = approval
    return approval


def new_id() -> str:
    return str(uuid4())


def get(approval_id: str) -> Optional[ApprovalRequest]:
    return approval_requests.get(approval_id)


def list_all() -> List[ApprovalRequest]:
    return sorted(
        approval_requests.values(),
        key=lambda approval: approval.created_at,
        reverse=True,
    )
