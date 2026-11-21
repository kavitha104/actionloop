import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.core.db import get_connection

class DigestAndReminderService:
    @staticmethod
    def get_upcoming_reminders(only_pending: bool = True) -> List[Dict[str, Any]]:
        conn = get_connection()
        c = conn.cursor()
        if only_pending:
            c.execute("SELECT * FROM reminders WHERE sent = 0 ORDER BY scheduled_date ASC")
        else:
            c.execute("SELECT * FROM reminders ORDER BY scheduled_date ASC")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    @staticmethod
    def dispatch_reminder(reminder_id: str) -> Optional[Dict[str, Any]]:
        conn = get_connection()
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute("""
            UPDATE reminders 
            SET sent = 1, sent_at = ? 
            WHERE id = ?
        """, (now, reminder_id))
        conn.commit()
        c.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def generate_person_digest(person: str) -> Dict[str, Any]:
        conn = get_connection()
        c = conn.cursor()

        # Fetch open tasks
        c.execute("SELECT * FROM tasks WHERE LOWER(owner) = LOWER(?) AND status = 'open' ORDER BY created_at DESC", (person,))
        open_tasks = [dict(r) for r in c.fetchall()]

        # Fetch completed tasks
        c.execute("SELECT * FROM tasks WHERE LOWER(owner) = LOWER(?) AND status = 'done' ORDER BY updated_at DESC", (person,))
        done_tasks = [dict(r) for r in c.fetchall()]

        # Fetch active decisions owned by person
        c.execute("SELECT * FROM decisions_memory WHERE LOWER(owner) = LOWER(?) AND is_superseded = 0 ORDER BY created_at DESC", (person,))
        owned_decisions = [dict(r) for r in c.fetchall()]

        conn.close()

        # Workload calculation
        workload_score = len(open_tasks)
        upcoming_deadlines = [t for t in open_tasks if t.get("deadline") and t.get("deadline") != "Not set"]

        summary_lines = [
            f"### Weekly Focus Digest for {person}",
            f"- **Active Commitments**: {len(open_tasks)} tasks open",
            f"- **Upcoming Deadlines**: {len(upcoming_deadlines)} critical items",
            f"- **Governing Decisions**: {len(owned_decisions)} active team agreements",
            ""
        ]

        if open_tasks:
            summary_lines.append("#### High Priority Deliverables:")
            for t in open_tasks:
                summary_lines.append(f"- [{t['external_ticket']}] **{t['title']}** (Due: {t['deadline']})")
        else:
            summary_lines.append("No pending open tasks! All deliverables up to date.")

        if owned_decisions:
            summary_lines.append("\n#### Active Team Directives Owned:")
            for d in owned_decisions:
                summary_lines.append(f"- *{d['text']}* ({d['meeting_title']}, {d['meeting_date']})")

        return {
            "person": person,
            "open_tasks": open_tasks,
            "completed_tasks": done_tasks,
            "owned_decisions": owned_decisions,
            "upcoming_deadlines_count": len(upcoming_deadlines),
            "workload_score": workload_score,
            "summary_markdown": "\n".join(summary_lines)
        }

    @classmethod
    def generate_team_digest(cls) -> Dict[str, Any]:
        conn = get_connection()
        c = conn.cursor()

        # Get all distinct owners from tasks and decisions
        c.execute("SELECT DISTINCT owner FROM tasks UNION SELECT DISTINCT owner FROM decisions_memory")
        all_people = [r[0] for r in c.fetchall() if r[0] and r[0].lower() not in ["unknown", "unassigned"]]
        
        if not all_people:
            all_people = ["Priya", "Arjun", "Sana", "Ravi"]

        # Fetch active unresolved conflicts
        c.execute("""
            SELECT c.*, m.title as meeting_title 
            FROM conflicts c
            JOIN meetings m ON c.meeting_id = m.id
            WHERE c.resolution IS NULL OR c.resolution = ''
        """)
        active_conflicts = [dict(r) for r in c.fetchall()]
        conn.close()

        workloads = {}
        digests = {}
        for p in all_people:
            d = cls.generate_person_digest(p)
            workloads[p] = d["workload_score"]
            digests[p] = d

        now = datetime.now()
        week_label = f"Week of {now.strftime('%b %d, %Y')}"

        return {
            "period": week_label,
            "team_members": all_people,
            "workloads": workloads,
            "member_digests": digests,
            "active_conflicts": active_conflicts
        }
