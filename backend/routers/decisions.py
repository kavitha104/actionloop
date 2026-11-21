from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.domain import Decision, Meeting
from backend.schemas.domain import DecisionRead

router = APIRouter(prefix="/decisions", tags=["decisions"])

@router.get("", response_model=List[DecisionRead])
def list_decisions(
    status: Optional[str] = None,
    topic: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Decision)
    if status:
        query = query.filter(Decision.status == status)
    if topic:
        query = query.filter(Decision.topic == topic)
    if search:
        s = f"%{search}%"
        query = query.filter((Decision.statement.ilike(s)) | (Decision.topic.ilike(s)))
    return query.order_by(Decision.id.desc()).all()

@router.get("/timeline")
def get_timeline(as_of: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Tier 2 Feature: Decision Time Machine.
    Scrub to any date and see what the team believed at that moment (which decisions were active).
    Superseded decisions fade out and appear in lineage chains.
    """
    all_decisions = db.query(Decision).join(Meeting).all()
    results = []
    for d in all_decisions:
        meeting_date = d.meeting.date if d.meeting else "2026-01-01"
        is_active_at_time = True
        if as_of and meeting_date > as_of:
            continue  # Created after the as_of date

        # If it was superseded, check when its successor was created
        if d.superseded_by:
            successor_date = d.superseded_by[0].meeting.date if d.superseded_by[0].meeting else "9999-99-99"
            if as_of and as_of >= successor_date:
                is_active_at_time = False

        results.append({
            "id": d.id,
            "statement": d.statement,
            "topic": d.topic,
            "made_by": d.made_by,
            "meeting_title": d.meeting.title if d.meeting else "Unknown",
            "meeting_date": meeting_date,
            "is_active_at_time": is_active_at_time,
            "current_status": d.status,
            "supersedes_id": d.supersedes_id
        })
    return {
        "as_of": as_of or "latest",
        "count": len(results),
        "decisions": results
    }

@router.get("/{decision_id}/lineage")
def get_decision_lineage(decision_id: int, db: Session = Depends(get_db)):
    """
    Fetches the entire predecessor and successor lineage graph for a decision.
    """
    d = db.query(Decision).filter(Decision.id == decision_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Decision not found")

    chain = []
    # Trace predecessors
    curr = d
    while curr:
        chain.insert(0, {
            "id": curr.id,
            "statement": curr.statement,
            "status": curr.status,
            "topic": curr.topic,
            "made_by": curr.made_by,
            "meeting_id": curr.meeting_id,
            "meeting_date": curr.meeting.date if curr.meeting else "N/A"
        })
        if curr.supersedes_id:
            curr = db.query(Decision).filter(Decision.id == curr.supersedes_id).first()
        else:
            break

    # Trace successors
    succ = db.query(Decision).filter(Decision.supersedes_id == d.id).first()
    while succ:
        chain.append({
            "id": succ.id,
            "statement": succ.statement,
            "status": succ.status,
            "topic": succ.topic,
            "made_by": succ.made_by,
            "meeting_id": succ.meeting_id,
            "meeting_date": succ.meeting.date if succ.meeting else "N/A"
        })
        succ = db.query(Decision).filter(Decision.supersedes_id == succ.id).first()

    return {
        "decision_id": decision_id,
        "lineage_depth": len(chain),
        "lineage_chain": chain
    }
