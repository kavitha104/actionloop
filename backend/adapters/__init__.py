from backend.adapters.tracker_base import TrackerAdapter, UnapprovedItemError
from backend.adapters.mock_tracker import MockTracker
from backend.adapters.github_tracker import GitHubTracker
from backend.adapters.notifier_base import NotifierBase
from backend.adapters.console_notifier import ConsoleNotifier
from backend.config import settings

def get_tracker_adapter() -> TrackerAdapter:
    if settings.tracker_integration.lower() == "github":
        return GitHubTracker()
    return MockTracker()

def get_notifier_adapter() -> NotifierBase:
    return ConsoleNotifier()

__all__ = [
    "TrackerAdapter", "UnapprovedItemError", "MockTracker", "GitHubTracker",
    "NotifierBase", "ConsoleNotifier", "get_tracker_adapter", "get_notifier_adapter"
]
