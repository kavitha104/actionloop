import datetime
import logging
from typing import List, Dict, Any, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from backend.database import SessionLocal
from backend.models.domain import ActionItem, OutboxItem, Person, AuditLog
from backend.adapters import get_notifier_adapter

logger = logging.getLogger("ActionLoopScheduler")

class SchedulerService:
    scheduler: Optional[BackgroundScheduler] = None

    @classmethod
    def start(cls):
        if cls.scheduler is None:
            cls.scheduler = BackgroundScheduler(daemon=True)
            # Scan reminders every 60 seconds
            cls.scheduler.add_job(cls.scan_and_queue_reminders, "interval", minutes=1, id="reminder_scan")
            cls.scheduler.start()
            logger.info("[SchedulerService] APScheduler background engine started.")

    @classmethod
    def shutdown(cls):
        if cls.scheduler and cls.scheduler.running:
            cls.scheduler.shutdown(wait=False)
            logger.info("[SchedulerService] Scheduler shut down cleanly.")

    @classmethod
    def scan_and_queue_reminders(cls) -> List[Dict[str, Any]]:
        """
        Scans all active action items and queues reminders at 3d, 1d, 0d, or overdue offsets.
        """
        db = SessionLocal()
        queued = []
        try:
            today = datetime.date.today()
            tasks = db.query(ActionItem).filter(
                ActionItem.status.in_(["approved", "posted"]),
                ActionItem.deadline.isnot(None),
                ActionItem.reminder_state.in_(["scheduled", "snoozed"])
            ).all()

            for task in tasks:
                try:
                    due_date = datetime.date.fromisoformat(task.deadline)
                except Exception:
                    continue

                diff_days = (due_date - today).days

                # Offsets check: 3 days, 1 day, morning of (0 days), overdue (< 0)
                should_remind = False
                reminder_label = ""
                if diff_days == 3:
                    should_remind = True
                    reminder_label = "3 days before deadline"
                elif diff_days == 1:
                    should_remind = True
                    reminder_label = "1 day before deadline"
                elif diff_days == 0:
                    should_remind = True
                    reminder_label = "morning of deadline"
                elif diff_days < 0:
                    should_remind = True
                    reminder_label = "overdue escalation"

                if should_remind:
                    # Check owner auto_remind preferences
                    person = db.query(Person).filter(Person.name == task.owner).first()
                    auto_send = person.auto_remind if person else False

                    # Check if reminder already queued recently to prevent duplicates
                    existing = db.query(OutboxItem).filter(
                        OutboxItem.type == "reminder",
                        OutboxItem.status.in_(["pending_confirmation", "sent"])
                    ).all()
                    already_queued = any(
                        o.payload.get("task_id") == task.id and o.payload.get("reminder_label") == reminder_label
                        for o in existing
                    )
                    if already_queued:
                        continue

                    payload = {
                        "task_id": task.id,
                        "title": f"Reminder: '{task.title}' is due {reminder_label}",
                        "body": f"Task '{task.title}' is assigned to {task.owner}. Deadline: {task.deadline}.",
                        "owner": task.owner,
                        "deadline": task.deadline,
                        "reminder_label": reminder_label
                    }

                    outbox_item = OutboxItem(
                        type="reminder",
                        payload=payload,
                        status="approved" if auto_send else "pending_confirmation",
                        destination="in_app"
                    )
                    db.add(outbox_item)
                    task.reminder_state = "reminded"
                    queued.append(payload)

            db.commit()
        except Exception as e:
            logger.error(f"[SchedulerService] Error in scan: {e}")
            db.rollback()
        finally:
            db.close()
        return queued

    @classmethod
    def snooze_task_reminder(cls, db: Session, task_id: int, days: int = 1) -> ActionItem:
        task = db.query(ActionItem).filter(ActionItem.id == task_id).first()
        if not task:
            raise ValueError(f"Task #{task_id} not found.")

        task.reminder_state = "snoozed"
        log = AuditLog(
            actor="User",
            action=f"snooze_reminder_{days}d",
            entity="ActionItem",
            entity_id=task.id,
            after_json=f'{{"snoozed_days": {days}, "reminder_state": "snoozed"}}'
        )
        db.add(log)
        db.commit()
        db.refresh(task)
        return task

    @classmethod
    def mark_task_done(cls, db: Session, task_id: int) -> ActionItem:
        task = db.query(ActionItem).filter(ActionItem.id == task_id).first()
        if not task:
            raise ValueError(f"Task #{task_id} not found.")

        task.status = "done"
        task.reminder_state = "done"
        log = AuditLog(
            actor="User",
            action="mark_task_done",
            entity="ActionItem",
            entity_id=task.id,
            after_json='{"status": "done"}'
        )
        db.add(log)
        db.commit()
        db.refresh(task)
        return task
