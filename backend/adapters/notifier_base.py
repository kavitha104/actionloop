from abc import ABC, abstractmethod
from typing import Dict, Any

class NotifierBase(ABC):
    @abstractmethod
    def send_notification(self, notification_type: str, recipient: str, title: str, body: str, metadata: Dict[str, Any], approval_status: str) -> Dict[str, Any]:
        """
        Sends an outbound notification (reminder, digest, conflict alert).
        MUST reject delivery if approval_status != 'approved'.
        """
        pass
