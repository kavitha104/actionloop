from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class UtteranceBase(BaseModel):
    speaker: str
    timestamp: Optional[str] = None
    text: str
    order_index: int = 0

class UtteranceCreate(UtteranceBase):
    pass

class UtteranceRead(UtteranceBase):
    id: int
    meeting_id: int

    class Config:
        from_attributes = True

class DecisionBase(BaseModel):
    statement: str
    rationale: Optional[str] = None
    topic: str = "general"
    made_by: Optional[str] = None
    status: str = "active"
    supersedes_id: Optional[int] = None
    source_utterance_ids: List[int] = []

class DecisionCreate(DecisionBase):
    meeting_id: int

class DecisionRead(DecisionBase):
    id: int
    meeting_id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ActionItemBase(BaseModel):
    title: str
    description: Optional[str] = None
    owner: Optional[str] = None
    needs_owner: bool = False
    deadline: Optional[str] = None
    raw_deadline_phrase: Optional[str] = None
    priority: str = "medium"
    status: str = "proposed"
    confidence: float = 1.0
    source_utterance_ids: List[int] = []
    tracker_ref: Optional[str] = None
    reminder_state: str = "scheduled"

class ActionItemCreate(ActionItemBase):
    meeting_id: int

class ActionItemUpdate(BaseModel):
    title: Optional[str] = None
    owner: Optional[str] = None
    needs_owner: Optional[bool] = None
    deadline: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None

class ActionItemRead(ActionItemBase):
    id: int
    meeting_id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class LooseEndRead(BaseModel):
    id: int
    meeting_id: int
    text: str
    source_utterance_ids: List[int] = []
    status: str = "open"
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ConflictRead(BaseModel):
    id: int
    new_item_type: str
    new_item_id: int
    existing_decision_id: int
    conflict_type: str
    severity: str
    explanation: str
    suggested_resolution: str
    resolution: str
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    existing_decision: Optional[DecisionRead] = None
    new_item_title: Optional[str] = None

    class Config:
        from_attributes = True

class ConflictResolveRequest(BaseModel):
    resolution: str  # supersede_old | keep_old | merge | dismiss
    resolved_by: str = "User"
    merge_statement: Optional[str] = None

class MeetingCreate(BaseModel):
    title: str
    date: Optional[str] = None
    project: Optional[str] = "General"
    raw_transcript: str
    speaker_mapping: Optional[Dict[str, str]] = None  # e.g. {"Unknown Speaker 1": "Arjun"}

class MeetingRead(BaseModel):
    id: int
    title: str
    date: str
    project: str
    participants: List[str]
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class MeetingDetail(MeetingRead):
    raw_transcript: str
    utterances: List[UtteranceRead] = []
    decisions: List[DecisionRead] = []
    action_items: List[ActionItemRead] = []
    loose_ends: List[LooseEndRead] = []
    conflicts: List[ConflictRead] = []

class PersonBase(BaseModel):
    name: str
    email: Optional[str] = None
    aliases: List[str] = []
    slack_handle: Optional[str] = None
    auto_remind: bool = True

class PersonRead(PersonBase):
    id: int

    class Config:
        from_attributes = True

class OutboxItemRead(BaseModel):
    id: int
    type: str
    payload: Dict[str, Any]
    status: str
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    destination: str
    external_ref: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class AuditLogRead(BaseModel):
    id: int
    actor: str
    action: str
    entity: str
    entity_id: Optional[int] = None
    before: Optional[Any] = None
    after: Optional[Any] = None
    timestamp: Optional[datetime] = None

    class Config:
        from_attributes = True

class HealthMetrics(BaseModel):
    decision_execution_rate: float
    on_time_task_rate: float
    open_conflicts_count: int
    decision_debt_count: int
    total_decisions: int
    total_action_items: int
    completed_action_items: int

class SearchCitation(BaseModel):
    meeting_id: int
    meeting_title: str
    meeting_date: str
    quote: str
    speaker: str
    item_type: str

class SearchAskResponse(BaseModel):
    query: str
    answer: str
    citations: List[SearchCitation] = []
