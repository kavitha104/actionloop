from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.domain import ActionItem, AuditLog
from backend.schemas.domain import ActionItemRead, ActionItemUpdate
from backend.services.scheduler_service import SchedulerService

router = APIRouter(tags=["tasks"])

@router.get("/tasks", response_model=List[ActionItemRead])
def list_tasks(
    owner: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(ActionItem)
    if owner:
        query = query.filter(ActionItem.owner == owner)
    if status:
        query = query.filter(ActionItem.status == status)
    return query.order_by(ActionItem.id.desc()).all()

@router.post("/tasks/{task_id}/toggle")
def toggle_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(ActionItem).filter(ActionItem.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    new_status = "done" if task.status != "done" else "posted"
    task.status = new_status
    if new_status == "done":
        task.reminder_state = "done"
    db.commit()
    return {"id": task.id, "status": task.status, "title": task.title}

@router.post("/tasks/{task_id}/snooze")
def snooze_task(task_id: int, days: int = Body(1, embed=True), db: Session = Depends(get_db)):
    try:
        updated = SchedulerService.snooze_task_reminder(db, task_id, days=days)
        return {"id": updated.id, "reminder_state": updated.reminder_state, "message": f"Snoozed for {days} day(s)."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/items/{item_id}/edit", response_model=ActionItemRead)
def edit_action_item(item_id: int, payload: ActionItemUpdate, db: Session = Depends(get_db)):
    act = db.query(ActionItem).filter(ActionItem.id == item_id).first()
    if not act:
        raise HTTPException(status_code=404, detail="Action item not found")

    if payload.title is not None:
        act.title = payload.title
    if payload.owner is not None:
        act.owner = payload.owner
        act.needs_owner = False
    if payload.needs_owner is not None:
        act.needs_owner = payload.needs_owner
    if payload.deadline is not None:
        act.deadline = payload.deadline
    if payload.priority is not None:
        act.priority = payload.priority
    if payload.status is not None:
        act.status = payload.status

    db.commit()
    db.refresh(act)
    return act
