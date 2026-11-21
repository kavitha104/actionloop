from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.domain import OutboxItem
from backend.schemas.domain import OutboxItemRead
from backend.services.outbox_service import OutboxService

router = APIRouter(prefix="/outbox", tags=["outbox"])

@router.get("", response_model=List[OutboxItemRead])
def list_outbox(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(OutboxItem)
    if status:
        query = query.filter(OutboxItem.status == status)
    return query.order_by(OutboxItem.id.desc()).all()

@router.post("/{item_id}/approve", response_model=OutboxItemRead)
def approve_outbox_item(
    item_id: int,
    payload: dict = Body(default={"approved_by": "User", "dry_run": False}),
    db: Session = Depends(get_db)
):
    try:
        approved_by = payload.get("approved_by", "User")
        dry_run = payload.get("dry_run", False)
        return OutboxService.approve_item(db, item_id, approved_by=approved_by, dry_run=dry_run)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{item_id}/reject", response_model=OutboxItemRead)
def reject_outbox_item(
    item_id: int,
    payload: dict = Body(default={"rejected_by": "User"}),
    db: Session = Depends(get_db)
):
    try:
        rejected_by = payload.get("rejected_by", "User")
        return OutboxService.reject_item(db, item_id, rejected_by=rejected_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/approve-all", response_model=List[OutboxItemRead])
def approve_all_outbox(
    payload: dict = Body(default={"approved_by": "User", "dry_run": False}),
    db: Session = Depends(get_db)
):
    approved_by = payload.get("approved_by", "User")
    dry_run = payload.get("dry_run", False)
    return OutboxService.approve_all(db, approved_by=approved_by, dry_run=dry_run)

@router.post("/dry-run")
def dry_run_simulation(db: Session = Depends(get_db)):
    """
    Simulates posting all pending outbox items without touching external APIs.
    """
    pending = db.query(OutboxItem).filter(OutboxItem.status == "pending_confirmation").all()
    preview = []
    for item in pending:
        preview.append({
            "id": item.id,
            "type": item.type,
            "destination": item.destination,
            "simulated_action": f"Would create ticket in {item.destination} for '{item.payload.get('title')}'",
            "assignee": item.payload.get("owner"),
            "due_date": item.payload.get("deadline")
        })
    return {
        "mode": "DRY_RUN",
        "pending_count": len(pending),
        "simulation_results": preview
    }
