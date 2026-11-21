import datetime
import json
from typing import List, Optional, Any
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey
)
from sqlalchemy.orm import relationship
from backend.database import Base

def current_utc():
    return datetime.datetime.now(datetime.timezone.utc)

class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    date = Column(String(50), nullable=False, default=lambda: datetime.date.today().isoformat())
    project = Column(String(100), default="General")
    participants_json = Column(Text, default="[]")  # List of names
    raw_transcript = Column(Text, nullable=False)
    status = Column(String(50), default="ingested")  # ingested | extracted | reviewed
    created_at = Column(DateTime, default=current_utc)

    utterances = relationship("Utterance", back_populates="meeting", cascade="all, delete-orphan")
    decisions = relationship("Decision", back_populates="meeting", cascade="all, delete-orphan")
    action_items = relationship("ActionItem", back_populates="meeting", cascade="all, delete-orphan")
    loose_ends = relationship("LooseEnd", back_populates="meeting", cascade="all, delete-orphan")

    @property
    def participants(self) -> List[str]:
        try:
            return json.loads(self.participants_json or "[]")
        except:
            return []

    @participants.setter
    def participants(self, val: List[str]):
        self.participants_json = json.dumps(val or [])


class Utterance(Base):
    __tablename__ = "utterances"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=False, index=True)
    speaker = Column(String(100), nullable=False)
    timestamp = Column(String(50), nullable=True)  # e.g., "00:12:03"
    text = Column(Text, nullable=False)
    order_index = Column(Integer, default=0)

    meeting = relationship("Meeting", back_populates="utterances")


class Decision(Base):
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=False, index=True)
    statement = Column(Text, nullable=False)
    rationale = Column(Text, nullable=True)
    topic = Column(String(100), index=True, default="general")
    made_by = Column(String(100), nullable=True)
    status = Column(String(50), default="active", index=True)  # active | superseded | reversed | conflicted
    supersedes_id = Column(Integer, ForeignKey("decisions.id"), nullable=True)
    embedding_json = Column(Text, nullable=True)  # list of floats serialized as json
    source_utterance_ids_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=current_utc)

    meeting = relationship("Meeting", back_populates="decisions")
    superseded_by = relationship("Decision", remote_side=[supersedes_id])

    @property
    def source_utterance_ids(self) -> List[int]:
        try:
            return json.loads(self.source_utterance_ids_json or "[]")
        except:
            return []

    @source_utterance_ids.setter
    def source_utterance_ids(self, val: List[int]):
        self.source_utterance_ids_json = json.dumps(val or [])

    @property
    def embedding(self) -> Optional[List[float]]:
        if not self.embedding_json:
            return None
        try:
            return json.loads(self.embedding_json)
        except:
            return None

    @embedding.setter
    def embedding(self, val: Optional[List[float]]):
        self.embedding_json = json.dumps(val) if val is not None else None


class ActionItem(Base):
    __tablename__ = "action_items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    owner = Column(String(100), nullable=True)
    needs_owner = Column(Boolean, default=False)
    deadline = Column(String(50), nullable=True)
    raw_deadline_phrase = Column(String(100), nullable=True)
    priority = Column(String(20), default="medium")  # low | medium | high | urgent
    status = Column(String(50), default="proposed", index=True)  # proposed | approved | posted | done | rejected
    confidence = Column(Float, default=1.0)
    source_utterance_ids_json = Column(Text, default="[]")
    tracker_ref = Column(String(100), nullable=True)
    reminder_state = Column(String(50), default="scheduled")  # scheduled | reminded | snoozed | done
    created_at = Column(DateTime, default=current_utc)

    meeting = relationship("Meeting", back_populates="action_items")

    @property
    def source_utterance_ids(self) -> List[int]:
        try:
            return json.loads(self.source_utterance_ids_json or "[]")
        except:
            return []

    @source_utterance_ids.setter
    def source_utterance_ids(self, val: List[int]):
        self.source_utterance_ids_json = json.dumps(val or [])


class LooseEnd(Base):
    __tablename__ = "loose_ends"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    source_utterance_ids_json = Column(Text, default="[]")
    status = Column(String(50), default="open")  # open | converted | dismissed
    created_at = Column(DateTime, default=current_utc)

    meeting = relationship("Meeting", back_populates="loose_ends")

    @property
    def source_utterance_ids(self) -> List[int]:
        try:
            return json.loads(self.source_utterance_ids_json or "[]")
        except:
            return []

    @source_utterance_ids.setter
    def source_utterance_ids(self, val: List[int]):
        self.source_utterance_ids_json = json.dumps(val or [])


class Conflict(Base):
    __tablename__ = "conflicts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    new_item_type = Column(String(50), nullable=False)  # decision | action_item
    new_item_id = Column(Integer, nullable=False)
    existing_decision_id = Column(Integer, ForeignKey("decisions.id"), nullable=False, index=True)
    conflict_type = Column(String(50), nullable=False)  # contradiction | duplicate | scope_change | owner_clash | deadline_clash
    severity = Column(String(20), default="warning")  # info | warning | critical / hard
    explanation = Column(Text, nullable=False)
    suggested_resolution = Column(String(50), default="supersede_old")
    resolution = Column(String(50), default="pending", index=True)  # pending | supersede_old | keep_old | merge | dismiss
    resolved_by = Column(String(100), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=current_utc)

    existing_decision = relationship("Decision")


class Person(Base):
    __tablename__ = "people"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    email = Column(String(255), nullable=True)
    aliases_json = Column(Text, default="[]")
    slack_handle = Column(String(100), nullable=True)
    auto_remind = Column(Boolean, default=True)

    @property
    def aliases(self) -> List[str]:
        try:
            return json.loads(self.aliases_json or "[]")
        except:
            return []

    @aliases.setter
    def aliases(self, val: List[str]):
        self.aliases_json = json.dumps(val or [])


class OutboxItem(Base):
    __tablename__ = "outbox_items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    type = Column(String(50), nullable=False)  # task | reminder | digest | notification
    payload_json = Column(Text, nullable=False)
    status = Column(String(50), default="pending_confirmation", index=True)  # pending_confirmation | approved | sent | rejected | failed
    approved_by = Column(String(100), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    destination = Column(String(100), default="tracker")  # tracker | email | slack
    external_ref = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=current_utc)

    @property
    def payload(self) -> Any:
        try:
            return json.loads(self.payload_json or "{}")
        except:
            return {}

    @payload.setter
    def payload(self, val: Any):
        self.payload_json = json.dumps(val or {})


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    actor = Column(String(100), default="System")
    action = Column(String(100), nullable=False)  # approve | reject | edit | supersede | resolve_conflict | send
    entity = Column(String(100), nullable=False)  # ActionItem | Decision | Conflict | OutboxItem
    entity_id = Column(Integer, nullable=True)
    before_json = Column(Text, nullable=True)
    after_json = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=current_utc)

    @property
    def before(self) -> Any:
        try:
            return json.loads(self.before_json) if self.before_json else None
        except:
            return None

    @before.setter
    def before(self, val: Any):
        self.before_json = json.dumps(val) if val is not None else None

    @property
    def after(self) -> Any:
        try:
            return json.loads(self.after_json) if self.after_json else None
        except:
            return None

    @after.setter
    def after(self, val: Any):
        self.after_json = json.dumps(val) if val is not None else None
