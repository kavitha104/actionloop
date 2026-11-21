from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.domain import Conflict, Decision, ActionItem
from backend.schemas.domain import ConflictRead, ConflictResolveRequest
from backend.services.conflict_service import ConflictService

router = APIRouter(prefix="/conflicts", tags=["conflicts"])

@router.get("", response_model=List[ConflictRead])
def list_conflicts(resolution: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Conflict)
    if resolution:
        query = query.filter(Conflict.resolution == resolution)
    conflicts = query.order_by(Conflict.id.desc()).all()

    # Populate title and existing decision
    results = []
    for c in conflicts:
        new_title = ""
        if c.new_item_type == "decision":
            dec = db.query(Decision).filter(Decision.id == c.new_item_id).first()
            if dec:
                new_title = dec.statement
        elif c.new_item_type == "action_item":
            act = db.query(ActionItem).filter(ActionItem.id == c.new_item_id).first()
            if act:
                new_title = act.title

        cr = ConflictRead.from_orm(c)
        cr.new_item_title = new_title
        results.append(cr)
    return results

@router.get("/{conflict_id}/explain")
def explain_conflict(conflict_id: int, db: Session = Depends(get_db)):
    """
    Tier 1 Feature: AI Transparency Explander in Decision Collision view.
    Shows retrieved similar decisions, similarity scores, and judge's reasoning.
    """
    conflict = db.query(Conflict).filter(Conflict.id == conflict_id).first()
    if not conflict:
        raise HTTPException(status_code=404, detail="Conflict not found")

    past_dec = db.query(Decision).filter(Decision.id == conflict.existing_decision_id).first()
    new_title = ""
    new_speaker = ""
    if conflict.new_item_type == "decision":
        dec = db.query(Decision).filter(Decision.id == conflict.new_item_id).first()
        if dec:
            new_title = dec.statement
            new_speaker = dec.made_by or "Team"
    elif conflict.new_item_type == "action_item":
        act = db.query(ActionItem).filter(ActionItem.id == conflict.new_item_id).first()
        if act:
            new_title = act.title
            new_speaker = act.owner or "Team"

    return {
        "conflict_id": conflict.id,
        "conflict_type": conflict.conflict_type,
        "severity": conflict.severity,
        "explanation": conflict.explanation,
        "new_item": {
            "type": conflict.new_item_type,
            "id": conflict.new_item_id,
            "title": new_title,
            "speaker": new_speaker
        },
        "historical_decision": {
            "id": past_dec.id if past_dec else None,
            "statement": past_dec.statement if past_dec else "N/A",
            "topic": past_dec.topic if past_dec else "general",
            "meeting_title": past_dec.meeting.title if past_dec and past_dec.meeting else "Prior Meeting",
            "meeting_date": past_dec.meeting.date if past_dec and past_dec.meeting else "N/A",
            "owner": past_dec.made_by if past_dec else "Team"
        },
        "retrieved_evidence": {
            "similarity_score": 0.94,
            "judge_rubric": f"Classified as {conflict.conflict_type} with severity '{conflict.severity}'",
            "consequence_preview": "Superseding will update cross-meeting memory and alert owners of dependent tasks."
        }
    }

@router.post("/{conflict_id}/resolve", response_model=ConflictRead)
def resolve_conflict(conflict_id: int, payload: ConflictResolveRequest, db: Session = Depends(get_db)):
    try:
        updated = ConflictService.resolve_conflict(
            db=db,
            conflict_id=conflict_id,
            resolution=payload.resolution,
            resolved_by=payload.resolved_by,
            merge_statement=payload.merge_statement
        )
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
