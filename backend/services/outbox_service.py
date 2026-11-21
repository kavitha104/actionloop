import json
import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.models.domain import OutboxItem, ActionItem, AuditLog, Conflict
from backend.adapters import get_tracker_adapter, get_notifier_adapter, UnapprovedItemError
from backend.config import settings

class OutboxService:
    @staticmethod
    def queue_task(db: Session, action_item: ActionItem) -> OutboxItem:
        """
        Stages an extracted action item into Outbox with status pending_confirmation.
        """
        payload = {
            "task_id": action_item.id,
            "meeting_id": action_item.meeting_id,
            "title": action_item.title,
            "description": action_item.description,
            "owner": action_item.owner,
            "deadline": action_item.deadline,
            "priority": action_item.priority,
            "needs_owner": action_item.needs_owner
        }
        item = OutboxItem(
            type="task",
            payload=payload,
            status="pending_confirmation",
            destination="tracker"
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @classmethod
    def approve_item(
        cls,
        db: Session,
        item_id: int,
        approved_by: str = "User",
        dry_run: bool = False
    ) -> OutboxItem:
        """
        Enforces human confirmation gate before ANY external posting.
        Verifies no unresolved blocking conflicts exist.
        """
        outbox_item = db.query(OutboxItem).filter(OutboxItem.id == item_id).first()
        if not outbox_item:
            raise ValueError(f"OutboxItem #{item_id} not found.")

        # Check for unresolved blocking conflicts on this item
        task_id = outbox_item.payload.get("task_id")
        if task_id:
            pending_conflict = db.query(Conflict).filter(
                Conflict.new_item_id == task_id,
                Conflict.resolution == "pending",
                Conflict.severity.in_(["critical", "hard", "warning"])
            ).first()
            if pending_conflict:
                raise ValueError(
                    f"Security Block: Cannot approve OutboxItem #{item_id} because of an unresolved "
                    f"conflict ({pending_conflict.conflict_type}: {pending_conflict.explanation}). "
                    "Resolve the conflict before confirming."
                )

        before_status = outbox_item.status
        outbox_item.status = "approved"
        outbox_item.approved_by = approved_by
        outbox_item.approved_at = datetime.datetime.now(datetime.timezone.utc)

        # Dispatch via configured adapter
        if dry_run or settings.dry_run:
            outbox_item.external_ref = f"DRYRUN-{outbox_item.id}"
            outbox_item.status = "sent"
        else:
            try:
                if outbox_item.type == "task":
                    tracker = get_tracker_adapter()
                    result = tracker.create_task(outbox_item.payload, approval_status=outbox_item.status)
                    outbox_item.external_ref = result.get("external_ref")
                    outbox_item.status = "sent"

                    # Update associated ActionItem
                    if task_id:
                        act = db.query(ActionItem).filter(ActionItem.id == task_id).first()
                        if act:
                            act.status = "posted"
                            act.tracker_ref = outbox_item.external_ref
                else:
                    notifier = get_notifier_adapter()
                    recipient = outbox_item.payload.get("owner") or outbox_item.payload.get("recipient", "Team")
                    title = outbox_item.payload.get("title", "ActionLoop Notification")
                    body = outbox_item.payload.get("description") or outbox_item.payload.get("body", "")
                    notifier.send_notification(
                        notification_type=outbox_item.type,
                        recipient=recipient,
                        title=title,
                        body=body,
                        metadata=outbox_item.payload,
                        approval_status=outbox_item.status
                    )
                    outbox_item.status = "sent"
                    outbox_item.external_ref = f"NOTIF-{outbox_item.id}"
            except Exception as e:
                outbox_item.status = "failed"
                outbox_item.error_message = str(e)
                db.commit()
                raise

        # Record in AuditLog
        log = AuditLog(
            actor=approved_by,
            action="approve_and_send",
            entity="OutboxItem",
            entity_id=outbox_item.id,
            before_json=json.dumps({"status": before_status}),
            after_json=json.dumps({
                "status": outbox_item.status,
                "external_ref": outbox_item.external_ref,
                "approved_by": approved_by
            })
        )
        db.add(log)
        db.commit()
        db.refresh(outbox_item)
        return outbox_item

    @classmethod
    def reject_item(cls, db: Session, item_id: int, rejected_by: str = "User") -> OutboxItem:
        outbox_item = db.query(OutboxItem).filter(OutboxItem.id == item_id).first()
        if not outbox_item:
            raise ValueError(f"OutboxItem #{item_id} not found.")

        before_status = outbox_item.status
        outbox_item.status = "rejected"
        outbox_item.approved_by = rejected_by
        outbox_item.approved_at = datetime.datetime.now(datetime.timezone.utc)

        task_id = outbox_item.payload.get("task_id")
        if task_id:
            act = db.query(ActionItem).filter(ActionItem.id == task_id).first()
            if act:
                act.status = "rejected"

        log = AuditLog(
            actor=rejected_by,
            action="reject_outbox_item",
            entity="OutboxItem",
            entity_id=outbox_item.id,
            before_json=json.dumps({"status": before_status}),
            after_json=json.dumps({"status": "rejected", "rejected_by": rejected_by})
        )
        db.add(log)
        db.commit()
        db.refresh(outbox_item)
        return outbox_item

    @classmethod
    def approve_all(cls, db: Session, approved_by: str = "User", dry_run: bool = False) -> List[OutboxItem]:
        pending = db.query(OutboxItem).filter(OutboxItem.status == "pending_confirmation").all()
        results = []
        for item in pending:
            try:
                approved = cls.approve_item(db, item.id, approved_by=approved_by, dry_run=dry_run)
                results.append(approved)
            except ValueError:
                # Skipped if blocked by conflict
                continue
        return results
