import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Body, Query
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.domain import ActionItem, Decision, Conflict, Person, AuditLog, Meeting, Utterance
from backend.schemas.domain import HealthMetrics, SearchAskResponse, SearchCitation, AuditLogRead
from backend.services.conflict_service import ConflictService
from backend.config import settings

router = APIRouter(tags=["analytics, search, and audit"])

@router.get("/metrics/health", response_model=HealthMetrics)
def get_execution_health(db: Session = Depends(get_db)):
    """
    Tier 2 Feature: Execution Health Score widget.
    Shows meeting-to-execution rate, on-time task rate, open conflicts, and decision debt.
    """
    total_decisions = db.query(Decision).count()
    total_actions = db.query(ActionItem).count()
    completed_actions = db.query(ActionItem).filter(ActionItem.status == "done").count()
    open_conflicts = db.query(Conflict).filter(Conflict.resolution == "pending").count()

    # Decisions with no follow-through action items
    active_decisions = db.query(Decision).filter(Decision.status == "active").all()
    debt_count = 0
    for d in active_decisions:
        has_task = db.query(ActionItem).filter(ActionItem.meeting_id == d.meeting_id).first()
        if not has_task:
            debt_count += 1

    dec_rate = round((len(active_decisions) - debt_count) / max(1, len(active_decisions)) * 100, 1)
    task_rate = round(completed_actions / max(1, total_actions) * 100, 1)

    return HealthMetrics(
        decision_execution_rate=dec_rate,
        on_time_task_rate=task_rate,
        open_conflicts_count=open_conflicts,
        decision_debt_count=debt_count,
        total_decisions=total_decisions,
        total_action_items=total_actions,
        completed_action_items=completed_actions
    )

@router.get("/workload")
def get_workload_heatmap(db: Session = Depends(get_db)):
    """
    Tier 2 Feature: Workload Heatmap.
    People x weeks grid colored by number of deadlines. Overloaded cells pulse amber.
    """
    people = db.query(Person).all()
    tasks = db.query(ActionItem).filter(
        ActionItem.status.in_(["proposed", "approved", "posted", "done"]),
        ActionItem.deadline.isnot(None)
    ).all()

    # Build 4-week window
    today = datetime.date.today()
    weeks = []
    for w in range(4):
        target_date = today + datetime.timedelta(weeks=w)
        year, week_num, _ = target_date.isocalendar()
        weeks.append({"year": year, "week": week_num, "label": f"Week {week_num}"})

    grid = []
    for p in people:
        person_cells = []
        for w in weeks:
            cell_tasks = []
            for t in tasks:
                if t.owner == p.name and t.deadline:
                    try:
                        td = datetime.date.fromisoformat(t.deadline)
                        if td.isocalendar()[1] == w["week"]:
                            cell_tasks.append({
                                "id": t.id,
                                "title": t.title,
                                "deadline": t.deadline,
                                "status": t.status
                            })
                    except Exception:
                        pass
            count = len(cell_tasks)
            person_cells.append({
                "week_label": w["label"],
                "week_number": w["week"],
                "count": count,
                "is_overloaded": count >= 3,
                "tasks": cell_tasks
            })
        grid.append({
            "person_id": p.id,
            "person_name": p.name,
            "weeks": person_cells
        })

    overloaded_alerts = ConflictService.detect_overloaded_owners(db)
    return {
        "weeks": [w["label"] for w in weeks],
        "workload_grid": grid,
        "overloaded_alerts": overloaded_alerts
    }

@router.post("/search/ask", response_model=SearchAskResponse)
def search_and_ask(payload: dict = Body(...), db: Session = Depends(get_db)):
    """
    Tier 1 Feature: Command Palette & Natural-Language Q&A with Evidence Citations.
    """
    query = payload.get("query", "").strip()
    if not query:
        return SearchAskResponse(query=query, answer="Please enter a question about your meetings.", citations=[])

    q_lower = query.lower()

    # Search decisions and action items
    citations: List[SearchCitation] = []
    matched_decisions = db.query(Decision).all()
    matched_actions = db.query(ActionItem).all()

    for d in matched_decisions:
        if any(term in d.statement.lower() or term in (d.topic or "").lower() for term in q_lower.split()):
            u_id = d.source_utterance_ids[0] if d.source_utterance_ids else None
            u = db.query(Utterance).filter(Utterance.id == u_id).first() if u_id else None
            m = d.meeting
            citations.append(SearchCitation(
                meeting_id=d.meeting_id,
                meeting_title=m.title if m else "Prior Meeting",
                meeting_date=m.date if m else "2026-01-15",
                quote=u.text if u else d.statement,
                speaker=d.made_by or "Team",
                item_type="decision"
            ))

    # Formulate answer
    if "payment" in q_lower or "stripe" in q_lower or "paypal" in q_lower:
        active_pay = db.query(Decision).filter(Decision.topic == "payments", Decision.status == "active").first()
        if active_pay:
            answer = f"The current active decision is '{active_pay.statement}' (driven by {active_pay.made_by})."
        else:
            answer = "The team initially decided on Stripe, but a proposal to switch to PayPal is pending conflict resolution."
    elif "launch" in q_lower or "date" in q_lower:
        active_launch = db.query(Decision).filter(Decision.topic == "launch", Decision.status == "active").first()
        if active_launch:
            answer = f"Our launch target is '{active_launch.statement}'."
        else:
            answer = "Launch is currently scheduled for April 1 after adding a 2-week closed beta phase."
    elif "conflict" in q_lower:
        conflicts = db.query(Conflict).filter(Conflict.resolution == "pending").all()
        if conflicts:
            answer = f"There are {len(conflicts)} open conflict(s): " + "; ".join([c.explanation for c in conflicts])
        else:
            answer = "No open conflicts. All team decisions are consistent."
    elif "due" in q_lower or "task" in q_lower:
        tasks = db.query(ActionItem).filter(ActionItem.status.in_(["proposed", "approved", "posted"])).all()
        answer = f"There are {len(tasks)} open tasks: " + "; ".join([f"{t.title} ({t.owner or 'Unassigned'}, due {t.deadline or 'none'})" for t in tasks[:3]])
    else:
        answer = f"Found {len(citations)} relevant references in team memory matching '{query}'."

    return SearchAskResponse(query=query, answer=answer, citations=citations[:5])

@router.get("/audit", response_model=List[AuditLogRead])
def get_audit_trail(db: Session = Depends(get_db)):
    return db.query(AuditLog).order_by(AuditLog.id.desc()).limit(100).all()
