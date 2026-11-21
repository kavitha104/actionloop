import logging
from typing import Dict, Any, List
from backend.adapters.notifier_base import NotifierBase
from backend.adapters.tracker_base import UnapprovedItemError

logger = logging.getLogger("ActionLoopNotifier")

class ConsoleNotifier(NotifierBase):
    """
    Default notifier that logs notifications to console and keeps an in-app
    notification center record.
    Enforces strict confirmation check.
    """
    def __init__(self):
        self.notification_history: List[Dict[str, Any]] = []

    def send_notification(self, notification_type: str, recipient: str, title: str, body: str, metadata: Dict[str, Any], approval_status: str) -> Dict[str, Any]:
        if approval_status != "approved":
            raise UnapprovedItemError(
                f"Security Gate Block: Cannot send notification ({notification_type}) to {recipient} "
                f"when approval_status='{approval_status}'."
            )

        record = {
            "id": len(self.notification_history) + 1,
            "type": notification_type,
            "recipient": recipient,
            "title": title,
            "body": body,
            "metadata": metadata,
            "status": "delivered"
        }
        self.notification_history.append(record)
        logger.info(f"[NOTIFIER DISPATCH] Type={notification_type} To={recipient} | Title: {title}")
        return record
