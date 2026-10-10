from typing import Any, Dict

from app.integrations.registry import get_email_adapter


def draft_email(**arguments: Any) -> Dict[str, Any]:
    return get_email_adapter().draft_email(**arguments)


def send_email(**arguments: Any) -> Dict[str, Any]:
    return get_email_adapter().send_email(**arguments)
