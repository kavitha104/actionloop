import uuid
import sqlite3
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.models.schemas import ExtractedItem, ConflictRecord, ConflictSeverity, ItemKind
from app.core.db import get_connection

class MemoryConflictService:
    @staticmethod
    def get_all_active_memory() -> List[Dict[str, Any]]:
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT id, meeting_id, meeting_title, meeting_date, text, owner, topic, topic_value, quote, is_superseded, superseded_by, created_at
            FROM decisions_memory
            WHERE is_superseded = 0
            ORDER BY created_at DESC
        """)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    @classmethod
    def detect_conflicts(cls, meeting_id: str, new_items: List[ExtractedItem]) -> List[ConflictRecord]:
        active_memory = cls.get_all_active_memory()
        conflicts: List[ConflictRecord] = []

        for item in new_items:
            # We look for conflicts if it's a decision OR an action touching an established architectural topic
            for mem in active_memory:
                # 1. Direct Topic Match Conflict Detection
                if item.topic and mem["topic"] and item.topic == mem["topic"]:
                    item_val = (item.topic_value or "").lower().strip()
                    mem_val = (mem["topic_value"] or "").lower().strip()

                    # Exact duplicate check
                    if item.text.lower().strip() == mem["text"].lower().strip() or (item_val and item_val == mem_val):
                        # Duplicate confirmation
                        conflicts.append(ConflictRecord(
                            conflict_id=f"cnf-{uuid.uuid4().hex[:8]}",
                            extracted_item_id=item.id,
                            topic=item.topic,
                            severity=ConflictSeverity.DUPLICATE,
                            new_text=item.text,
                            new_owner=item.owner,
                            new_deadline=item.deadline,
                            existing_memory_id=mem["id"],
                            existing_meeting_title=mem["meeting_title"],
                            existing_meeting_date=mem["meeting_date"],
                            existing_text=mem["text"],
                            existing_owner=mem["owner"],
                            reason=f"This re-states the existing decision from '{mem['meeting_title']}' ({mem['meeting_date']})."
                        ))
                    elif item_val and mem_val and item_val != mem_val:
                        # Hard contradiction on a single-choice decision topic
                        topic_display = item.topic.replace("_", " ").title()
                        conflicts.append(ConflictRecord(
                            conflict_id=f"cnf-{uuid.uuid4().hex[:8]}",
                            extracted_item_id=item.id,
                            topic=item.topic,
                            severity=ConflictSeverity.HARD,
                            new_text=item.text,
                            new_owner=item.owner,
                            new_deadline=item.deadline,
                            existing_memory_id=mem["id"],
                            existing_meeting_title=mem["meeting_title"],
                            existing_meeting_date=mem["meeting_date"],
                            existing_text=mem["text"],
                            existing_owner=mem["owner"],
                            reason=f"Contradicts earlier decision on {topic_display}: previously set to '{mem_val}', now proposed as '{item_val}'."
                        ))

                # 2. Textual / Semantic Keyword overlap (e.g. database, launch, pricing)
                elif not item.topic:
                    common_keywords = ["launch", "database", "pricing", "slack", "discord", "auth", "mobile"]
                    for kw in common_keywords:
                        if kw in item.text.lower() and kw in mem["text"].lower():
                            # Potential soft conflict
                            conflicts.append(ConflictRecord(
                                conflict_id=f"cnf-{uuid.uuid4().hex[:8]}",
                                extracted_item_id=item.id,
                                topic=kw,
                                severity=ConflictSeverity.SOFT,
                                new_text=item.text,
                                new_owner=item.owner,
                                new_deadline=item.deadline,
                                existing_memory_id=mem["id"],
                                existing_meeting_title=mem["meeting_title"],
                                existing_meeting_date=mem["meeting_date"],
                                existing_text=mem["text"],
                                existing_owner=mem["owner"],
                                reason=f"Mentions '{kw}', which was previously governed by '{mem['text']}' in {mem['meeting_title']}."
                            ))
                            break

        return conflicts

    @staticmethod
    def record_decision(meeting_id: str, meeting_title: str, meeting_date: str, text: str, owner: str, topic: Optional[str], topic_val: Optional[str], quote: Optional[str], conn: Optional[sqlite3.Connection] = None) -> str:
        should_close = False
        if conn is None:
            conn = get_connection()
            should_close = True
        c = conn.cursor()
        mem_id = f"mem-{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()

        # If this is a new topic decision, mark old active decisions for this topic as superseded
        if topic:
            c.execute("""
                UPDATE decisions_memory 
                SET is_superseded = 1, superseded_by = ?
                WHERE topic = ? AND is_superseded = 0
            """, (mem_id, topic))

        c.execute("""
            INSERT INTO decisions_memory (id, meeting_id, meeting_title, meeting_date, text, owner, topic, topic_value, quote, is_superseded, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        """, (mem_id, meeting_id, meeting_title, meeting_date, text, owner, topic, topic_val, quote, now))

        if should_close:
            conn.commit()
            conn.close()
        return mem_id
