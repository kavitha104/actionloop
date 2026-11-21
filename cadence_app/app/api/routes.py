import os
import json
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from app.models.schemas import (
    IngestTranscriptRequest, IngestTranscriptResponse,
    ConfirmAndPostRequest, ConfirmAndPostResponse,
    ExtractedItem, ConflictRecord, TrackerType, TaskStatus
)
from app.core.db import get_connection
from app.services.extraction_service import ExtractionService
from app.services.conflict_service import MemoryConflictService
from app.services.tracker_service import TrackerService
from app.services.digest_service import DigestAndReminderService

router = APIRouter(prefix="/api", tags=["Cadence Core Agent"])

@router.post("/ingest", response_model=IngestTranscriptResponse)
def ingest_transcript(payload: IngestTranscriptRequest):
    """
    Step 1 & 2: Ingest raw transcript with speaker attribution.
    Extract decisions, action items, owners, deadlines.
    Step 3: Compare against cross-meeting memory to detect contradictions and duplicates.
    Requires human confirmation before anything is posted to tracker or memory.
    """
    meeting_id = f"mtg-{uuid.uuid4().hex[:8]}"
    now = datetime.now()
    meeting_date = payload.meeting_date or now.strftime("%b %d, %Y")
    
    conn = get_connection()
    c = conn.cursor()

    # Store meeting
    c.execute("""
        INSERT INTO meetings (id, title, meeting_date, transcript_raw, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (meeting_id, payload.meeting_title, meeting_date, payload.transcript_text, payload.source, now.isoformat()))

    # Extract items
    items = ExtractionService.extract_items_from_transcript(payload.transcript_text)

    # Persist extracted items to staging table
    for it in items:
        c.execute("""
            INSERT INTO extracted_items (id, meeting_id, kind, text, owner, deadline, topic, topic_value, quote, speaker, confidence, is_selected, is_confirmed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (it.id, meeting_id, it.kind.value, it.text, it.owner, it.deadline, it.topic, it.topic_value, it.quote, it.speaker, it.confidence, 1 if it.is_selected else 0))

    # Detect conflicts against cross-meeting memory
    conflicts = MemoryConflictService.detect_conflicts(meeting_id, items)

    # Store conflicts
    for cf in conflicts:
        c.execute("""
            INSERT INTO conflicts (conflict_id, meeting_id, extracted_item_id, topic, severity, new_text, new_owner, new_deadline, existing_memory_id, existing_meeting_title, existing_meeting_date, existing_text, existing_owner, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (cf.conflict_id, meeting_id, cf.extracted_item_id, cf.topic, cf.severity.value, cf.new_text, cf.new_owner, cf.new_deadline, cf.existing_memory_id, cf.existing_meeting_title, cf.existing_meeting_date, cf.existing_text, cf.existing_owner, cf.reason))

    # Log ingestion audit
    c.execute("""
        INSERT INTO audit_logs (event_type, description, details_json, created_at)
        VALUES ('INGEST_TRANSCRIPT', ?, ?, ?)
    """, (f"Ingested transcript for '{payload.meeting_title}' with {len(items)} items and {len(conflicts)} detected conflicts", json.dumps({"meeting_id": meeting_id, "items": len(items), "conflicts": len(conflicts)}), now.isoformat()))

    conn.commit()
    conn.close()

    return IngestTranscriptResponse(
        meeting_id=meeting_id,
        meeting_title=payload.meeting_title,
        meeting_date=meeting_date,
        items=items,
        conflicts=conflicts,
        unresolved_conflicts_count=len(conflicts),
        summary={
            "decisions_count": len([i for i in items if i.kind.value == "dec"]),
            "action_items_count": len([i for i in items if i.kind.value == "act"]),
            "hard_conflicts_count": len([c for c in conflicts if c.severity.value == "hard"]),
            "duplicate_count": len([c for c in conflicts if c.severity.value == "dup"]),
            "speakers_involved": list(set([i.speaker for i in items if i.speaker]))
        }
    )

@router.post("/confirm-and-post", response_model=ConfirmAndPostResponse)
def confirm_and_post(payload: ConfirmAndPostRequest):
    """
    Step 4 & 5: Human confirmation gate before anything gets posted!
    1. Updates items with user overrides (modified owners, deadlines, or toggled off).
    2. Applies conflict resolutions (e.g. keep new, keep old).
    3. Posts tasks to configured tracker (Linear, Jira, Asana, etc.).
    4. Commits confirmed decisions into cross-meeting persistent memory.
    5. Sets up scheduled reminders.
    """
    conn = get_connection()
    c = conn.cursor()

    # Verify meeting exists
    c.execute("SELECT * FROM meetings WHERE id = ?", (payload.meeting_id,))
    meeting_row = c.fetchone()
    if not meeting_row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Meeting {payload.meeting_id} not found")
    
    meeting_dict = dict(meeting_row)
    now = datetime.now()

    # Apply conflict resolutions
    kept_existing_item_ids = set()
    for res in payload.conflict_resolutions:
        c.execute("""
            UPDATE conflicts 
            SET resolution = ?, resolved_at = ?
            WHERE conflict_id = ?
        """, (res.action, now.isoformat(), res.conflict_id))

        if res.action == "keep_existing":
            c.execute("SELECT extracted_item_id FROM conflicts WHERE conflict_id = ?", (res.conflict_id,))
            row = c.fetchone()
            if row:
                kept_existing_item_ids.add(row[0])

    posted_tasks = []
    posted_decisions_count = 0

    # Process items approved by user
    for it in payload.items:
        # Check if deselected or overridden by conflict resolution
        if not it.is_selected or it.id in kept_existing_item_ids:
            continue

        if it.kind.value == "act":
            # Create task in tracker
            task = TrackerService.create_task(
                meeting_id=payload.meeting_id,
                tracker=payload.tracker_type,
                title=it.text,
                owner=it.owner,
                deadline=it.deadline,
                conn=conn
            )
            posted_tasks.append(task)
        elif it.kind.value == "dec":
            # Commit to cross-meeting memory
            topic, topic_val = ExtractionService.extract_topic_and_value(it.text)
            MemoryConflictService.record_decision(
                meeting_id=payload.meeting_id,
                meeting_title=meeting_dict["title"],
                meeting_date=meeting_dict["meeting_date"],
                text=it.text,
                owner=it.owner,
                topic=topic,
                topic_val=topic_val,
                quote=f"Approved from {meeting_dict['title']}",
                conn=conn
            )
            posted_decisions_count += 1

    # Mark meeting items confirmed
    c.execute("UPDATE extracted_items SET is_confirmed = 1 WHERE meeting_id = ?", (payload.meeting_id,))
    
    # Audit log
    c.execute("""
        INSERT INTO audit_logs (event_type, description, details_json, created_at)
        VALUES ('CONFIRM_AND_POST', ?, ?, ?)
    """, (f"Confirmed and posted {len(posted_tasks)} tasks to {payload.tracker_type.value} and {posted_decisions_count} decisions into memory.", json.dumps({"meeting_id": payload.meeting_id, "tasks": len(posted_tasks)}), now.isoformat()))

    conn.commit()
    conn.close()

    return ConfirmAndPostResponse(
        meeting_id=payload.meeting_id,
        status="success",
        posted_tasks_count=len(posted_tasks),
        posted_decisions_count=posted_decisions_count,
        tracker=payload.tracker_type.value,
        tasks=posted_tasks,
        message=f"Successfully approved and posted {len(posted_tasks)} tasks to {payload.tracker_type.value}. Memory updated."
    )

@router.get("/memory")
def get_cross_meeting_memory(include_superseded: bool = False, topic: Optional[str] = None):
    """
    Returns the persistent cross-meeting decisions stored in memory.
    """
    conn = get_connection()
    c = conn.cursor()
    query = "SELECT * FROM decisions_memory WHERE 1=1"
    params = []

    if not include_superseded:
        query += " AND is_superseded = 0"
    if topic:
        query += " AND LOWER(topic) = LOWER(?)"
        params.append(topic)

    query += " ORDER BY created_at DESC"
    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"decisions": rows, "count": len(rows)}

@router.get("/conflicts")
def get_all_conflicts(only_unresolved: bool = True):
    """
    Returns detected cross-meeting conflicts and their status.
    """
    conn = get_connection()
    c = conn.cursor()
    if only_unresolved:
        c.execute("""
            SELECT c.*, m.title as meeting_title 
            FROM conflicts c
            JOIN meetings m ON c.meeting_id = m.id
            WHERE c.resolution IS NULL OR c.resolution = ''
            ORDER BY c.conflict_id DESC
        """)
    else:
        c.execute("""
            SELECT c.*, m.title as meeting_title 
            FROM conflicts c
            JOIN meetings m ON c.meeting_id = m.id
            ORDER BY c.conflict_id DESC
        """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"conflicts": rows, "count": len(rows)}

@router.get("/tasks")
def get_tracker_tasks(status: Optional[str] = None):
    """
    Returns all tracker tasks created across meetings.
    """
    tasks = TrackerService.get_all_tasks(status=status)
    return {"tasks": tasks, "count": len(tasks)}

@router.patch("/tasks/{task_id}/status")
def update_task_status(task_id: str, status: str = Query(..., description="open, in_progress, done")):
    """
    Update status of an external task ticket.
    """
    updated = TrackerService.update_task_status(task_id, status)
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "success", "task": updated}

@router.get("/reminders")
def get_reminders(only_pending: bool = True):
    """
    Returns automated reminders scheduled for upcoming deadlines.
    """
    reminders = DigestAndReminderService.get_upcoming_reminders(only_pending=only_pending)
    return {"reminders": reminders, "count": len(reminders)}

@router.post("/reminders/{reminder_id}/send")
def trigger_reminder(reminder_id: str):
    """
    Dispatches a deadline reminder notification.
    """
    res = DigestAndReminderService.dispatch_reminder(reminder_id)
    if not res:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"status": "dispatched", "reminder": res}

@router.get("/digest/team")
def get_team_weekly_digest():
    """
    Generates a full team weekly workload & progress digest.
    """
    return DigestAndReminderService.generate_team_digest()

@router.get("/digest/person/{person_name}")
def get_person_weekly_digest(person_name: str):
    """
    Generates an individualized weekly digest for a specific team member.
    """
    return DigestAndReminderService.generate_person_digest(person_name)

@router.get("/audit-logs")
def get_audit_logs():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 50")
    logs = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"logs": logs}
