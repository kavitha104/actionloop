import pytest
from backend.adapters.mock_tracker import MockTracker
from backend.adapters.console_notifier import ConsoleNotifier
from backend.adapters.tracker_base import UnapprovedItemError
from backend.database import SessionLocal
from backend.models.domain import OutboxItem, ActionItem, Conflict, Decision, AuditLog
from backend.services.outbox_service import OutboxService
from seed import seed_database

@pytest.fixture(autouse=True)
def setup_seed():
    seed_database()

def test_tracker_adapter_refuses_unapproved():
    tracker = MockTracker()
    payload = {"title": "Test Task", "owner": "Arjun"}
    
    # Must raise UnapprovedItemError when status is 'pending_confirmation'
    with pytest.raises(UnapprovedItemError) as exc_info:
        tracker.create_task(payload, approval_status="pending_confirmation")
    assert "Security Gate Block" in str(exc_info.value)

    # Must raise when status is 'proposed'
    with pytest.raises(UnapprovedItemError):
        tracker.create_task(payload, approval_status="proposed")

    # Succeeds ONLY when status is 'approved'
    result = tracker.create_task(payload, approval_status="approved")
    assert result["sync_status"] == "synced"
    assert result["external_ref"].startswith("MOCK-")

def test_notifier_adapter_refuses_unapproved():
    notifier = ConsoleNotifier()
    
    with pytest.raises(UnapprovedItemError) as exc:
        notifier.send_notification(
            notification_type="reminder",
            recipient="Arjun",
            title="Due Soon",
            body="Task due",
            metadata={},
            approval_status="pending_confirmation"
        )
    assert "Security Gate Block" in str(exc.value)

    # Succeeds when approved
    res = notifier.send_notification(
        notification_type="reminder",
        recipient="Arjun",
        title="Due Soon",
        body="Task due",
        metadata={},
        approval_status="approved"
    )
    assert res["status"] == "delivered"

def test_outbox_blocks_on_unresolved_conflict():
    db = SessionLocal()
    try:
        # Create an action item and an unresolved conflict
        dec = db.query(Decision).first()
        act = ActionItem(
            meeting_id=dec.meeting_id,
            title="Contradictory payment task",
            owner="Arjun",
            status="proposed"
        )
        db.add(act)
        db.flush()

        conf = Conflict(
            new_item_type="action_item",
            new_item_id=act.id,
            existing_decision_id=dec.id,
            conflict_type="contradiction",
            severity="critical",
            explanation="Unresolved contradiction",
            resolution="pending"
        )
        db.add(conf)
        db.flush()

        outbox = OutboxService.queue_task(db, act)
        assert outbox.status == "pending_confirmation"

        # Attempt to approve should fail
        with pytest.raises(ValueError) as exc:
            OutboxService.approve_item(db, outbox.id, approved_by="Priya")
        assert "unresolved conflict" in str(exc.value).lower()

        # Resolve conflict, then approval must succeed
        conf.resolution = "supersede_old"
        db.commit()

        approved = OutboxService.approve_item(db, outbox.id, approved_by="Priya")
        assert approved.status == "sent"
        assert approved.external_ref is not None
    finally:
        db.close()
