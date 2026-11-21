from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

class ItemKind(str, Enum):
    DECISION = "dec"
    ACTION = "act"

class ConflictSeverity(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    DUPLICATE = "dup"

class TaskStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"

class TrackerType(str, Enum):
    INTERNAL = "internal"
    LINEAR = "Linear"
    JIRA = "Jira"
    ASANA = "Asana"
    GITHUB = "GitHub"

class ExtractedItem(BaseModel):
    id: str
    kind: ItemKind
    text: str
    owner: str
    deadline: Optional[str] = None
    topic: Optional[str] = None
    topic_value: Optional[str] = None
    quote: str
    speaker: str
    confidence: float = 0.85
    is_selected: bool = True

class ConflictRecord(BaseModel):
    conflict_id: str
    extracted_item_id: str
    topic: str
    severity: ConflictSeverity
    new_text: str
    new_owner: str
    new_deadline: Optional[str] = None
    existing_memory_id: str
    existing_meeting_title: str
    existing_meeting_date: str
    existing_text: str
    existing_owner: str
    reason: str
    resolution: Optional[str] = None  # 'keep_new', 'keep_existing', 'both', 'dismissed'

class IngestTranscriptRequest(BaseModel):
    meeting_title: str = "Sprint Sync & Planning"
    meeting_date: Optional[str] = None
    transcript_text: str
    source: str = "text" # text, audio, upload

class IngestTranscriptResponse(BaseModel):
    meeting_id: str
    meeting_title: str
    meeting_date: str
    items: List[ExtractedItem]
    conflicts: List[ConflictRecord]
    unresolved_conflicts_count: int
    summary: Dict[str, Any]

class ConfirmResolution(BaseModel):
    conflict_id: str
    action: str # "keep_new" | "keep_existing" | "both" | "dismissed"

class EditableItemPayload(BaseModel):
    id: str
    kind: ItemKind
    text: str
    owner: str
    deadline: Optional[str] = None
    is_selected: bool = True

class ConfirmAndPostRequest(BaseModel):
    meeting_id: str
    items: List[EditableItemPayload]
    conflict_resolutions: List[ConfirmResolution] = []
    tracker_type: TrackerType = TrackerType.LINEAR
    tracker_project_key: Optional[str] = "CAD"
    enable_auto_reminders: bool = True

class ConfirmAndPostResponse(BaseModel):
    meeting_id: str
    status: str
    posted_tasks_count: int
    posted_decisions_count: int
    tracker: str
    tasks: List[Dict[str, Any]]
    message: str

class DecisionMemoryItem(BaseModel):
    id: str
    meeting_id: str
    meeting_title: str
    meeting_date: str
    text: str
    owner: str
    topic: Optional[str] = None
    topic_value: Optional[str] = None
    quote: Optional[str] = None
    is_superseded: bool = False
    superseded_by: Optional[str] = None
    created_at: str

class TrackerTaskItem(BaseModel):
    id: str
    external_ticket: str
    meeting_id: str
    tracker: str
    title: str
    owner: str
    deadline: Optional[str] = None
    status: TaskStatus
    reminder_sent: bool = False
    created_at: str

class DigestPersonResponse(BaseModel):
    person: str
    open_tasks: List[Dict[str, Any]]
    completed_tasks: List[Dict[str, Any]]
    owned_decisions: List[Dict[str, Any]]
    upcoming_deadlines_count: int
    workload_score: int
    summary_markdown: str

class TeamDigestResponse(BaseModel):
    period: str
    team_members: List[str]
    workloads: Dict[str, int]
    member_digests: Dict[str, DigestPersonResponse]
    active_conflicts: List[Dict[str, Any]]

class ReminderItem(BaseModel):
    id: str
    task_id: str
    external_ticket: str
    recipient: str
    title: str
    deadline: str
    scheduled_date: str
    sent: bool
    sent_at: Optional[str] = None
    message: str
