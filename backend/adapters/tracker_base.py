from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class UnapprovedItemError(PermissionError):
    """Raised when an attempt is made to post an unapproved item externally."""
    pass

class TrackerAdapter(ABC):
    @abstractmethod
    def create_task(self, item_payload: Dict[str, Any], approval_status: str) -> Dict[str, Any]:
        """
        Creates a task in the target tracker system.
        MUST refuse execution if approval_status != 'approved'.
        Returns dict with keys: {'external_ref': str, 'url': str, 'sync_status': str}
        """
        pass

    @abstractmethod
    def get_task(self, tracker_ref: str) -> Optional[Dict[str, Any]]:
        """Fetch remote task status if available."""
        pass

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """Verify tracker configuration and connectivity."""
        pass
