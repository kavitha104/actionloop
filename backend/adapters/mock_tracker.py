import uuid
from typing import Dict, Any, Optional
from backend.adapters.tracker_base import TrackerAdapter, UnapprovedItemError

class MockTracker(TrackerAdapter):
    """
    Default mock tracker adapter that creates tracked tickets in the local database
    and renders on the interactive board in the frontend.
    Strictly verifies approval_status == 'approved'.
    """
    def __init__(self):
        # In-memory ticket registry for simulated sync state
        self._synced_tickets: Dict[str, Dict[str, Any]] = {}
        self._seq = 101

    def create_task(self, item_payload: Dict[str, Any], approval_status: str) -> Dict[str, Any]:
        if approval_status != "approved":
            raise UnapprovedItemError(
                f"Security Gate Block: Cannot post to MockTracker when approval_status='{approval_status}'. "
                "Explicit human approval is strictly required."
            )

        task_id = item_payload.get("task_id") or str(uuid.uuid4())[:8]
        ticket_key = f"MOCK-{self._seq}"
        self._seq += 1

        ticket_data = {
            "external_ref": ticket_key,
            "title": item_payload.get("title", "Untitled Task"),
            "description": item_payload.get("description", ""),
            "assignee": item_payload.get("owner", "Unassigned"),
            "due_date": item_payload.get("deadline", "None"),
            "priority": item_payload.get("priority", "medium"),
            "status": "todo",
            "url": f"https://mocktracker.internal/browse/{ticket_key}",
            "sync_status": "synced"
        }
        self._synced_tickets[ticket_key] = ticket_data
        return ticket_data

    def get_task(self, tracker_ref: str) -> Optional[Dict[str, Any]]:
        return self._synced_tickets.get(tracker_ref)

    def test_connection(self) -> Dict[str, Any]:
        return {
            "status": "connected",
            "provider": "MockTracker",
            "message": "Local tracker active and ready for sync."
        }
