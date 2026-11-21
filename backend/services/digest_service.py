import os
import re
import json
import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from backend.models.domain import Person, ActionItem, Decision, Conflict, OutboxItem
from backend.config import settings

class DigestService:
    @classmethod
    def generate_digest_for_person(cls, db: Session, person_id: int) -> Dict[str, Any]:
        person = db.query(Person).filter(Person.id == person_id).first()
        if not person:
            raise ValueError(f"Person #{person_id} not found.")

        # Calculate dates
        today = datetime.date.today()
        seven_days_later = today + datetime.timedelta(days=7)

        # 1. Tasks due this week and overdue
        all_person_tasks = db.query(ActionItem).filter(
            ActionItem.owner == person.name
        ).all()

        due_this_week = []
        overdue = []
        newly_assigned = []
        for t in all_person_tasks:
            if t.status in ["done", "rejected"]:
                continue
            if t.deadline:
                try:
                    d = datetime.date.fromisoformat(t.deadline)
                    if d < today:
                        overdue.append(t)
                    elif today <= d <= seven_days_later:
                        due_this_week.append(t)
                except Exception:
                    due_this_week.append(t)
            else:
                due_this_week.append(t)

            # Newly assigned in past 7 days
            if t.created_at:
                created_date = t.created_at.date() if isinstance(t.created_at, datetime.datetime) else t.created_at
                if (today - created_date).days <= 7:
                    newly_assigned.append(t)

        # 2. Decisions that affect them (decisions they made or active in the project)
        relevant_decisions = db.query(Decision).filter(
            Decision.status == "active"
        ).order_by(Decision.id.desc()).limit(5).all()

        # 3. Unresolved conflicts
        unresolved_conflicts = db.query(Conflict).filter(
            Conflict.resolution == "pending"
        ).all()

        # 4. Decisions superseded since last week
        superseded_decisions = db.query(Decision).filter(
            Decision.status == "superseded"
        ).limit(3).all()

        # Generate 3-sentence summary
        summary = cls._generate_summary(
            person_name=person.name,
            due_tasks=due_this_week,
            overdue_tasks=overdue,
            decisions=relevant_decisions,
            conflicts=unresolved_conflicts
        )

        # Build HTML Email markup
        html_email = cls._render_html_email(
            person=person,
            summary=summary,
            due_tasks=due_this_week,
            overdue_tasks=overdue,
            decisions=relevant_decisions
        )

        # Story Cards sequence (for Tier 2 feature: Weekly Digest as story cards)
        story_cards = [
            {
                "id": "numbers",
                "badge": "Snapshot",
                "title": "Your Week in Numbers",
                "metric": f"{len(due_this_week)} due",
                "subtext": f"{len(overdue)} overdue · {len(relevant_decisions)} active decisions tracking"
            },
            {
                "id": "due_soon",
                "badge": "Priority",
                "title": "Due This Week",
                "items": [{"title": t.title, "due": t.deadline or "No date", "priority": t.priority} for t in due_this_week[:4]]
            },
            {
                "id": "overdue",
                "badge": "Attention",
                "title": "Overdue & Escalations",
                "items": [{"title": t.title, "due": t.deadline or "Overdue"} for t in overdue[:4]]
            },
            {
                "id": "decisions",
                "badge": "Memory",
                "title": "Decisions Affecting You",
                "items": [{"statement": d.statement, "topic": d.topic} for d in relevant_decisions[:3]]
            }
        ]

        digest_payload = {
            "person_id": person.id,
            "person_name": person.name,
            "email": person.email,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "summary": summary,
            "due_tasks": [{"id": t.id, "title": t.title, "deadline": t.deadline, "status": t.status} for t in due_this_week],
            "overdue_tasks": [{"id": t.id, "title": t.title, "deadline": t.deadline} for t in overdue],
            "relevant_decisions": [{"id": d.id, "statement": d.statement, "topic": d.topic} for d in relevant_decisions],
            "unresolved_conflicts_count": len(unresolved_conflicts),
            "superseded_count": len(superseded_decisions),
            "html_email": html_email,
            "story_cards": story_cards
        }

        # Stage digest in Outbox as pending confirmation
        outbox_item = OutboxItem(
            type="digest",
            payload=digest_payload,
            status="pending_confirmation",
            destination="email"
        )
        db.add(outbox_item)
        db.commit()
        db.refresh(outbox_item)

        digest_payload["outbox_item_id"] = outbox_item.id
        return digest_payload

    @classmethod
    def _generate_summary(cls, person_name: str, due_tasks: List[ActionItem], overdue_tasks: List[ActionItem], decisions: List[Decision], conflicts: List[Conflict]) -> str:
        if not settings.demo_mode and settings.gemini_api_key:
            try:
                from google import genai
                client = genai.Client(api_key=settings.gemini_api_key)
                prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "digest_v1.md")
                with open(prompt_path, "r", encoding="utf-8") as f:
                    template = f.read()

                prompt = (
                    template
                    .replace("{{person_name}}", person_name)
                    .replace("{{due_tasks}}", ", ".join([t.title for t in due_tasks]) or "None")
                    .replace("{{overdue_tasks}}", ", ".join([t.title for t in overdue_tasks]) or "None")
                    .replace("{{decisions}}", ", ".join([d.statement for d in decisions]) or "None")
                    .replace("{{conflicts}}", f"{len(conflicts)} open conflicts")
                )

                res = client.models.generate_content(
                    model=settings.gemini_model,
                    contents=prompt,
                    config={"response_mime_type": "application/json", "temperature": 0.2}
                )
                data = json.loads(res.text.strip())
                return data.get("summary", "")
            except Exception:
                pass

        # Deterministic 3-sentence summary
        s1 = f"You have {len(due_tasks)} action items due this week" + (f" and {len(overdue_tasks)} overdue tasks requiring immediate attention." if overdue_tasks else ".")
        s2 = f"Key team commitments include '{decisions[0].statement}'." if decisions else "All roadmap commitments are stable."
        s3 = f"Please review the pending decisions and resolve any open conflicts before sprint lock." if conflicts else "Your execution runway looks clear for the upcoming sprint."
        return f"{s1} {s2} {s3}"

    @staticmethod
    def _render_html_email(person: Person, summary: str, due_tasks: List[ActionItem], overdue_tasks: List[ActionItem], decisions: List[Decision]) -> str:
        tasks_html = "".join([
            f"<li style='margin-bottom:8px'><b>{t.title}</b> &mdash; <span style='color:#b5541a'>Due: {t.deadline or 'None'}</span></li>"
            for t in due_tasks
        ]) or "<li>No tasks due this week.</li>"

        decisions_html = "".join([
            f"<li style='margin-bottom:6px'><b>[{d.topic.upper()}]</b> {d.statement}</li>"
            for d in decisions
        ]) or "<li>No new decisions.</li>"

        return f"""
        <div style="font-family:'Instrument Sans',-apple-system,sans-serif;max-width:600px;margin:0 auto;padding:24px;background:#FAF8F3;color:#1B1A17;border-radius:16px;border:1px solid #E6E1D5">
          <div style="display:flex;align-items:center;margin-bottom:16px;">
            <div style="width:28px;height:28px;border-radius:6px;background:#0F6B5C;color:#fff;display:inline-flex;align-items:center;justify-content:center;font-weight:bold;margin-right:8px;">A</div>
            <h2 style="margin:0;font-size:20px;color:#1B1A17;">ActionLoop &middot; Weekly Execution Digest</h2>
          </div>
          <p style="font-size:14px;color:#6F695D;margin-top:0;">Prepared for <b>{person.name}</b> ({person.email or 'N/A'})</p>
          
          <div style="background:#FFFFFF;border:1px solid #E6E1D5;border-radius:12px;padding:16px;margin-bottom:20px;">
            <h3 style="margin:0 0 8px 0;font-size:14px;text-transform:uppercase;letter-spacing:0.05em;color:#0F6B5C;">Executive Summary</h3>
            <p style="margin:0;font-size:15px;line-height:1.5;">{summary}</p>
          </div>

          <h3 style="font-size:16px;margin:16px 0 8px 0;">Tasks Due This Week</h3>
          <ul style="padding-left:20px;font-size:14px;">{tasks_html}</ul>

          <h3 style="font-size:16px;margin:16px 0 8px 0;">Active Decisions</h3>
          <ul style="padding-left:20px;font-size:14px;">{decisions_html}</ul>

          <hr style="border:none;border-top:1px solid #E6E1D5;margin:24px 0 16px 0;" />
          <p style="font-size:12px;color:#6F695D;margin:0;">ActionLoop Meeting-to-Execution Agent &middot; Confidential &middot; Staged via Human Confirmation Airlock</p>
        </div>
        """
