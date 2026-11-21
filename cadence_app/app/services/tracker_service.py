import uuid
import sqlite3
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from app.core.db import get_connection
from app.models.schemas import TaskStatus, TrackerType

class TrackerService:
    @staticmethod
    def get_tracker_prefix(tracker: TrackerType) -> str:
        prefixes = {
            TrackerType.LINEAR: "LIN",
            TrackerType.JIRA: "JRA",
            TrackerType.ASANA: "ASA",
            TrackerType.GITHUB: "GH",
            TrackerType.INTERNAL: "CAD"
        }
        return prefixes.get(tracker, "TASK")

    @classmethod
    def get_next_ticket_number(cls, prefix: str, conn: Optional[sqlite3.Connection] = None) -> str:
        should_close = False
        if conn is None:
            conn = get_connection()
            should_close = True
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM tasks")
        count = c.fetchone()[0] + 101
        if should_close:
            conn.close()
        return f"{prefix}-{count}"

    @classmethod
    def create_task(cls, meeting_id: str, tracker: TrackerType, title: str, owner: str, deadline: Optional[str] = None, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        should_close = False
        if conn is None:
            conn = get_connection()
            should_close = True
        c = conn.cursor()
        task_id = f"tsk-{uuid.uuid4().hex[:8]}"
        prefix = cls.get_tracker_prefix(tracker)
        ticket_key = cls.get_next_ticket_number(prefix, conn=conn)
        now = datetime.now().isoformat()

        c.execute("""
            INSERT INTO tasks (id, external_ticket, meeting_id, tracker, title, owner, deadline, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (task_id, ticket_key, meeting_id, tracker.value, title, owner, deadline or "Not set", TaskStatus.OPEN.value, now, now))

        # Schedule automated reminder 1 day before deadline (or immediate if soon/not set)
        rem_id = f"rem-{uuid.uuid4().hex[:8]}"
        sched_time = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d %H:%M")
        msg = f"Reminder for {owner}: Task [{ticket_key}] '{title}' has a scheduled milestone/deadline: {deadline or 'Upcoming'}."
        
        c.execute("""
            INSERT INTO reminders (id, task_id, external_ticket, recipient, title, deadline, scheduled_date, sent, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
        """, (rem_id, task_id, ticket_key, owner, title, deadline or "Flexible", sched_time, msg))

        # Log audit entry
        c.execute("""
            INSERT INTO audit_logs (event_type, description, details_json, created_at)
            VALUES ('TASK_CREATED', ?, ?, ?)
        """, (f"Created {tracker.value} ticket {ticket_key} for {owner}", f'{{"task_id":"{task_id}","title":"{title}"}}', now))

        if should_close:
            conn.commit()
            conn.close()

        return {
            "id": task_id,
            "external_ticket": ticket_key,
            "tracker": tracker.value,
            "title": title,
            "owner": owner,
            "deadline": deadline or "Not set",
            "status": TaskStatus.OPEN.value,
            "created_at": now
        }

    @staticmethod
    def get_all_tasks(status: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = get_connection()
        c = conn.cursor()
        if status:
            c.execute("SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC", (status,))
        else:
            c.execute("SELECT * FROM tasks ORDER BY created_at DESC")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    @staticmethod
    def update_task_status(task_id: str, new_status: str) -> Optional[Dict[str, Any]]:
        conn = get_connection()
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ? OR external_ticket = ?", (new_status, now, task_id, task_id))
        conn.commit()
        c.execute("SELECT * FROM tasks WHERE id = ? OR external_ticket = ?", (task_id, task_id))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None
