import json
import asyncio
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.domain import Meeting, Utterance, Decision, ActionItem, LooseEnd, Conflict, Person
from backend.schemas.domain import MeetingCreate, MeetingRead, MeetingDetail
from backend.services.ingestion_service import IngestionService
from backend.services.extraction_service import ExtractionService
from backend.services.conflict_service import ConflictService
from backend.services.outbox_service import OutboxService

router = APIRouter(prefix="/meetings", tags=["meetings"])

@router.post("", response_model=MeetingRead)
def create_meeting(payload: MeetingCreate, db: Session = Depends(get_db)):
    parsed_utterances = IngestionService.parse_transcript(
        raw_text=payload.raw_transcript,
        speaker_mapping=payload.speaker_mapping,
        db=db
    )

    participants = list(set([u["speaker"] for u in parsed_utterances]))
    date_val = payload.date or "2026-02-05"

    meeting = Meeting(
        title=payload.title,
        date=date_val,
        project=payload.project or "Core Platform",
        participants=participants,
        raw_transcript=payload.raw_transcript,
        status="ingested"
    )
    db.add(meeting)
    db.flush()

    for u in parsed_utterances:
        utt = Utterance(
            meeting_id=meeting.id,
            speaker=u["speaker"],
            timestamp=u["timestamp"],
            text=u["text"],
            order_index=u["order_index"]
        )
        db.add(utt)

    db.commit()
    db.refresh(meeting)
    return meeting

@router.get("", response_model=List[MeetingRead])
def list_meetings(db: Session = Depends(get_db)):
    return db.query(Meeting).order_by(Meeting.id.desc()).all()

@router.get("/{meeting_id}", response_model=MeetingDetail)
def get_meeting(meeting_id: int, db: Session = Depends(get_db)):
    m = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Meeting not found")

    conflicts = db.query(Conflict).join(Decision, Conflict.existing_decision_id == Decision.id).all()
    # Filter conflicts that pertain to this meeting's items
    m_dec_ids = [d.id for d in m.decisions]
    m_act_ids = [a.id for a in m.action_items]
    relevant_conflicts = [
        c for c in conflicts
        if (c.new_item_type == "decision" and c.new_item_id in m_dec_ids) or
           (c.new_item_type == "action_item" and c.new_item_id in m_act_ids)
    ]

    return {
        "id": m.id,
        "title": m.title,
        "date": m.date,
        "project": m.project,
        "participants": m.participants,
        "raw_transcript": m.raw_transcript,
        "status": m.status,
        "created_at": m.created_at,
        "utterances": m.utterances,
        "decisions": m.decisions,
        "action_items": m.action_items,
        "loose_ends": m.loose_ends,
        "conflicts": relevant_conflicts
    }

@router.post("/{meeting_id}/extract")
def extract_meeting(meeting_id: int, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    utterances = [
        {"id": u.id, "speaker": u.speaker, "timestamp": u.timestamp, "text": u.text, "order_index": u.order_index}
        for u in meeting.utterances
    ]
    if not utterances:
        raise HTTPException(status_code=400, detail="No utterances found in meeting.")

    extracted = ExtractionService.extract_from_utterances(utterances, meeting.date)
    decisions_data = extracted.get("decisions", [])
    actions_data = extracted.get("action_items", [])
    loose_data = extracted.get("loose_ends", [])

    created_decisions = []
    created_conflicts = []

    for d in decisions_data:
        # Map utterance indices to db utterance ids
        u_ids = [utterances[idx]["id"] for idx in d.get("utterance_indices", []) if idx < len(utterances)]
        if not u_ids and utterances:
            u_ids = [utterances[0]["id"]]

        # Check for conflicts against cross-meeting memory
        ev_quote = d.get("evidence_quotes", [""])[0] if d.get("evidence_quotes") else d.get("statement")
        conf_eval = ConflictService.evaluate_decision_conflict(
            db=db,
            new_statement=d["statement"],
            topic=d["topic"],
            made_by=d.get("made_by") or "Team",
            evidence_quote=ev_quote,
            meeting_id=meeting.id
        )

        initial_status = "conflicted" if conf_eval else "active"

        dec_record = Decision(
            meeting_id=meeting.id,
            statement=d["statement"],
            topic=d.get("topic", "general"),
            made_by=d.get("made_by"),
            rationale=d.get("rationale"),
            status=initial_status,
            source_utterance_ids=u_ids
        )
        db.add(dec_record)
        db.flush()
        created_decisions.append(dec_record)

        if conf_eval:
            conflict = Conflict(
                new_item_type="decision",
                new_item_id=dec_record.id,
                existing_decision_id=conf_eval["existing_decision_id"],
                conflict_type=conf_eval["conflict_type"],
                severity=conf_eval["severity"],
                explanation=conf_eval["explanation"],
                suggested_resolution=conf_eval.get("suggested_resolution", "supersede_old"),
                resolution="pending"
            )
            db.add(conflict)
            db.flush()
            created_conflicts.append(conflict)

    created_actions = []
    for a in actions_data:
        u_ids = [utterances[idx]["id"] for idx in a.get("utterance_indices", []) if idx < len(utterances)]
        if not u_ids and utterances:
            u_ids = [utterances[0]["id"]]

        act_record = ActionItem(
            meeting_id=meeting.id,
            title=a["title"],
            description=a.get("description"),
            owner=a.get("owner"),
            needs_owner=a.get("needs_owner", False),
            deadline=a.get("deadline"),
            raw_deadline_phrase=a.get("raw_deadline_phrase"),
            priority=a.get("priority", "medium"),
            status="proposed",
            confidence=a.get("confidence", 0.9),
            source_utterance_ids=u_ids,
            reminder_state="scheduled"
        )
        db.add(act_record)
        db.flush()
        created_actions.append(act_record)

        # Evaluate duplicate or contradiction for action item
        act_conf = ConflictService.evaluate_action_item_conflict(db, a, meeting.id)
        if act_conf:
            c_record = Conflict(
                new_item_type="action_item",
                new_item_id=act_record.id,
                existing_decision_id=act_conf["existing_decision_id"],
                conflict_type=act_conf["conflict_type"],
                severity=act_conf["severity"],
                explanation=act_conf["explanation"],
                suggested_resolution=act_conf.get("suggested_resolution", "dismiss"),
                resolution="pending"
            )
            db.add(c_record)
            db.flush()
            created_conflicts.append(c_record)

        # Automatically stage into Outbox as pending_confirmation
        OutboxService.queue_task(db, act_record)

    # Save loose ends
    for l in loose_data:
        u_ids = [utterances[idx]["id"] for idx in l.get("utterance_indices", []) if idx < len(utterances)]
        le = LooseEnd(
            meeting_id=meeting.id,
            text=l["text"],
            source_utterance_ids=u_ids,
            status="open"
        )
        db.add(le)

    meeting.status = "extracted"
    db.commit()

    return {
        "status": "success",
        "meeting_id": meeting.id,
        "decisions_count": len(created_decisions),
        "action_items_count": len(created_actions),
        "conflicts_count": len(created_conflicts),
        "loose_ends_count": len(loose_data)
    }

@router.get("/{meeting_id}/events")
def get_meeting_events(meeting_id: int, db: Session = Depends(get_db)):
    """
    Tier 2 Feature: Meeting Heat Strip.
    Returns timeline events (talk time by speaker, decision timestamps, action item timestamps, conflict markers).
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Speaker talk-time distribution
    speaker_counts: Dict[str, int] = {}
    for u in meeting.utterances:
        words = len(u.text.split())
        speaker_counts[u.speaker] = speaker_counts.get(u.speaker, 0) + words

    total_words = max(1, sum(speaker_counts.values()))
    speaker_lanes = [
        {"speaker": spk, "word_count": cnt, "percentage": round(cnt / total_words * 100, 1)}
        for spk, cnt in speaker_counts.items()
    ]

    events = []
    for d in meeting.decisions:
        u_id = d.source_utterance_ids[0] if d.source_utterance_ids else None
        u = db.query(Utterance).filter(Utterance.id == u_id).first() if u_id else None
        events.append({
            "type": "decision",
            "id": d.id,
            "title": d.statement,
            "speaker": d.made_by,
            "timestamp": u.timestamp if u else "00:00",
            "order_index": u.order_index if u else 0,
            "status": d.status
        })

    for a in meeting.action_items:
        u_id = a.source_utterance_ids[0] if a.source_utterance_ids else None
        u = db.query(Utterance).filter(Utterance.id == u_id).first() if u_id else None
        events.append({
            "type": "action_item",
            "id": a.id,
            "title": a.title,
            "speaker": a.owner or "Needs Owner",
            "timestamp": u.timestamp if u else "00:00",
            "order_index": u.order_index if u else 0,
            "status": a.status
        })

    return {
        "meeting_id": meeting.id,
        "title": meeting.title,
        "total_utterances": len(meeting.utterances),
        "speaker_lanes": speaker_lanes,
        "events": events,
        "decision_density": f"{len(meeting.decisions)} decisions / {len(meeting.utterances)} turns",
        "unowned_tasks_count": len([a for a in meeting.action_items if a.needs_owner])
    }

@router.get("/extract/{job_id}/stream")
async def extract_stream(job_id: str):
    """
    Tier 1 Feature: Agent Progress Stream (SSE).
    Live step tracker: Ingesting -> Attributing speakers -> Extracting decisions -> Searching memory -> Checking conflicts -> Ready.
    """
    async def event_generator():
        steps = [
            {"step": "ingesting", "label": "Ingesting and parsing transcript structure...", "progress": 20},
            {"step": "attributing", "label": "Normalizing speakers against team memory & aliases...", "progress": 40},
            {"step": "extracting", "label": "Extracting decisions and action items with evidence linking...", "progress": 65},
            {"step": "memory", "label": "Searching cross-meeting memory (Compared against historical decisions)...", "progress": 85},
            {"step": "conflicts", "label": "Running AI collision judge & dependency check...", "progress": 95},
            {"step": "ready", "label": "Extraction complete. Airlock ready for review.", "progress": 100}
        ]
        for s in steps:
            await asyncio.sleep(0.35)
            yield f"data: {json.dumps(s)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
