import os
import re
import json
import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.models.domain import Decision, ActionItem, Conflict, AuditLog, Utterance
from backend.services.memory_service import MemoryService
from backend.config import settings

class ConflictService:
    @classmethod
    def evaluate_decision_conflict(
        cls,
        db: Session,
        new_statement: str,
        topic: str,
        made_by: str,
        evidence_quote: str,
        meeting_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves top similar active decisions and judges conflict.
        """
        similar = MemoryService.search_similar_decisions(
            db=db,
            query_text=new_statement,
            topic=topic,
            top_k=3,
            active_only=True
        )

        for candidate, sim_score in similar:
            if candidate.meeting_id == meeting_id:
                continue  # Skip decisions made within the same meeting

            # Run LLM judge or deterministic judge
            judge_res = cls._judge_pair(
                new_item_type="decision",
                new_item_text=new_statement,
                past_decision=candidate,
                sim_score=sim_score
            )
            if judge_res.get("has_conflict"):
                return {
                    "existing_decision_id": candidate.id,
                    "conflict_type": judge_res["conflict_type"],
                    "severity": judge_res["severity"],
                    "explanation": judge_res["explanation"],
                    "suggested_resolution": judge_res.get("suggested_resolution", "supersede_old"),
                    "consequence_preview": judge_res.get("consequence_preview", ""),
                    "similarity_score": sim_score
                }

        return None

    @classmethod
    def evaluate_action_item_conflict(
        cls,
        db: Session,
        new_action: Dict[str, Any],
        meeting_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Checks for duplicate tasks or deadline / dependency clashes.
        """
        title = new_action.get("title", "")
        owner = new_action.get("owner")
        deadline = new_action.get("deadline")

        # 1. Check duplicate task across active action items
        existing_actions = db.query(ActionItem).filter(
            ActionItem.status.in_(["proposed", "approved", "posted"]),
            ActionItem.meeting_id != meeting_id
        ).all()

        for ea in existing_actions:
            # Check near-exact or semantic duplicate
            t1 = title.lower()
            t2 = ea.title.lower()
            if t1 == t2 or (len(t1) > 10 and (t1 in t2 or t2 in t1)):
                # Link to a related decision or candidate decision
                dummy_dec = db.query(Decision).filter(Decision.meeting_id == ea.meeting_id).first()
                dec_id = dummy_dec.id if dummy_dec else 1
                return {
                    "existing_decision_id": dec_id,
                    "conflict_type": "duplicate",
                    "severity": "info",
                    "explanation": f"Duplicate task detected: '{ea.title}' was already assigned to {ea.owner} (Due: {ea.deadline}).",
                    "suggested_resolution": "dismiss",
                    "consequence_preview": "Discard this duplicate task to prevent duplicate tickets."
                }

        # 2. Check contradiction against active decisions (e.g. PayPal task when Stripe is active decision)
        similar_dec = MemoryService.search_similar_decisions(db, title, top_k=2, active_only=True)
        for cand, sim_score in similar_dec:
            if cand.meeting_id == meeting_id:
                continue
            judge_res = cls._judge_pair("action_item", title, cand, sim_score)
            if judge_res.get("has_conflict"):
                return {
                    "existing_decision_id": cand.id,
                    "conflict_type": judge_res["conflict_type"],
                    "severity": judge_res["severity"],
                    "explanation": judge_res["explanation"],
                    "suggested_resolution": judge_res.get("suggested_resolution", "supersede_old"),
                    "consequence_preview": judge_res.get("consequence_preview", ""),
                    "similarity_score": sim_score
                }

        return None

    @classmethod
    def _judge_pair(
        cls,
        new_item_type: str,
        new_item_text: str,
        past_decision: Decision,
        sim_score: float
    ) -> Dict[str, Any]:
        """
        Evaluates a pair using Gemini API if configured or deterministic rule rubric.
        """
        if not settings.demo_mode and settings.gemini_api_key:
            try:
                return cls._judge_with_gemini(new_item_type, new_item_text, past_decision)
            except Exception as e:
                print(f"[ConflictService] Gemini judge failed: {e}. Falling back to deterministic rubric.")

        return cls._judge_deterministic(new_item_type, new_item_text, past_decision, sim_score)

    @classmethod
    def _judge_with_gemini(cls, new_item_type: str, new_item_text: str, past_decision: Decision) -> Dict[str, Any]:
        from google import genai
        client = genai.Client(api_key=settings.gemini_api_key)

        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "conflict_judge_v1.md")
        with open(prompt_path, "r", encoding="utf-8") as f:
            template = f.read()

        prompt = (
            template
            .replace("{{new_item_type}}", new_item_type)
            .replace("{{new_item_text}}", new_item_text)
            .replace("{{new_item_owner}}", "N/A")
            .replace("{{new_item_deadline}}", "N/A")
            .replace("{{past_decision_id}}", str(past_decision.id))
            .replace("{{past_decision_statement}}", past_decision.statement)
            .replace("{{past_decision_topic}}", past_decision.topic or "")
            .replace("{{past_decision_made_by}}", past_decision.made_by or "Team")
            .replace("{{past_decision_quote}}", past_decision.rationale or "")
        )

        res = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0.0}
        )
        return json.loads(res.text.strip())

    @classmethod
    def _judge_deterministic(
        cls,
        new_item_type: str,
        new_item_text: str,
        past_decision: Decision,
        sim_score: float
    ) -> Dict[str, Any]:
        new_lower = new_item_text.lower()
        past_lower = past_decision.statement.lower()

        # 1. Contradiction: Payment providers (Stripe vs PayPal)
        if ("paypal" in new_lower and "stripe" in past_lower) or ("stripe" in new_lower and "paypal" in past_lower):
            return {
                "has_conflict": True,
                "conflict_type": "contradiction",
                "severity": "critical",
                "explanation": (
                    f"New item proposes switching to PayPal, which directly contradicts the active decision "
                    f"'{past_decision.statement}' (made by {past_decision.made_by})."
                ),
                "suggested_resolution": "supersede_old",
                "consequence_preview": "The earlier Stripe decision will be marked 'superseded'; linked tasks will be flagged."
            }

        # 2. Contradiction: Database choices (MongoDB vs Postgres vs MySQL)
        db_engines = ["postgres", "postgresql", "mysql", "mongodb", "dynamodb"]
        new_dbs = [d for d in db_engines if d in new_lower]
        past_dbs = [d for d in db_engines if d in past_lower]
        if new_dbs and past_dbs and set(new_dbs) != set(past_dbs):
            return {
                "has_conflict": True,
                "conflict_type": "contradiction",
                "severity": "critical",
                "explanation": f"Proposes {new_dbs[0].title()} which contradicts prior decision to use {past_dbs[0].title()}.",
                "suggested_resolution": "supersede_old",
                "consequence_preview": f"Marks '{past_decision.statement}' as superseded."
            }

        # 3. Launch date changes / Scope changes
        if "launch" in new_lower and "launch" in past_lower:
            # Check if different dates
            date_regex = re.compile(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}\b')
            d_new = date_regex.findall(new_lower)
            d_old = date_regex.findall(past_lower)
            if d_new and d_old and d_new != d_old:
                return {
                    "has_conflict": True,
                    "conflict_type": "scope_change",
                    "severity": "warning",
                    "explanation": f"Launch date shift detected between '{new_item_text}' and active target '{past_decision.statement}'.",
                    "suggested_resolution": "supersede_old",
                    "consequence_preview": "Updates roadmap target; checks dependent task deadlines."
                }

        # 4. Duplicate
        if sim_score > 0.88 or new_lower == past_lower:
            return {
                "has_conflict": True,
                "conflict_type": "duplicate",
                "severity": "info",
                "explanation": f"Item restates active decision: '{past_decision.statement}'.",
                "suggested_resolution": "dismiss",
                "consequence_preview": "No change needed; existing decision remains active."
            }

        return {"has_conflict": False, "conflict_type": "none", "severity": "info", "explanation": "Compatible"}

    @classmethod
    def resolve_conflict(
        cls,
        db: Session,
        conflict_id: int,
        resolution: str,
        resolved_by: str = "User",
        merge_statement: Optional[str] = None
    ) -> Conflict:
        """
        Executes user decision on conflict:
        - supersede_old: marks old decision 'superseded', activates new item, creates lineage chain
        - keep_old: leaves old decision 'active', marks new item as rejected/superseded
        - merge: updates old decision statement with merged text
        - dismiss: marks conflict dismissed
        Logs everything to AuditLog.
        """
        conflict = db.query(Conflict).filter(Conflict.id == conflict_id).first()
        if not conflict:
            raise ValueError(f"Conflict #{conflict_id} not found.")

        old_decision = db.query(Decision).filter(Decision.id == conflict.existing_decision_id).first()
        before_state = {
            "conflict_id": conflict.id,
            "resolution": conflict.resolution,
            "old_decision_status": old_decision.status if old_decision else None
        }

        conflict.resolution = resolution
        conflict.resolved_by = resolved_by
        conflict.resolved_at = datetime.datetime.now(datetime.timezone.utc)

        if resolution == "supersede_old" and old_decision:
            old_decision.status = "superseded"
            if conflict.new_item_type == "decision":
                new_dec = db.query(Decision).filter(Decision.id == conflict.new_item_id).first()
                if new_dec:
                    new_dec.supersedes_id = old_decision.id
                    new_dec.status = "active"

        elif resolution == "keep_old":
            if conflict.new_item_type == "decision":
                new_dec = db.query(Decision).filter(Decision.id == conflict.new_item_id).first()
                if new_dec:
                    new_dec.status = "rejected"
            elif conflict.new_item_type == "action_item":
                new_act = db.query(ActionItem).filter(ActionItem.id == conflict.new_item_id).first()
                if new_act:
                    new_act.status = "rejected"

        elif resolution == "merge" and old_decision and merge_statement:
            old_decision.statement = merge_statement

        # Add AuditLog entry
        log = AuditLog(
            actor=resolved_by,
            action=f"resolve_conflict_{resolution}",
            entity="Conflict",
            entity_id=conflict.id,
            before_json=json.dumps(before_state),
            after_json=json.dumps({
                "resolution": resolution,
                "resolved_by": resolved_by,
                "old_decision_status": old_decision.status if old_decision else None
            })
        )
        db.add(log)
        db.commit()
        db.refresh(conflict)
        return conflict

    @classmethod
    def detect_overloaded_owners(cls, db: Session) -> List[Dict[str, Any]]:
        """
        Detects team members overloaded with > 2 deadlines in the same calendar week.
        """
        active_tasks = db.query(ActionItem).filter(
            ActionItem.status.in_(["proposed", "approved", "posted"]),
            ActionItem.owner.isnot(None),
            ActionItem.deadline.isnot(None)
        ).all()

        from collections import defaultdict
        # Map (owner, year, week_num) -> list of tasks
        workloads = defaultdict(list)
        for t in active_tasks:
            try:
                d = datetime.date.fromisoformat(t.deadline)
                cal = d.isocalendar()
                key = (t.owner, cal[0], cal[1])
                workloads[key].append(t)
            except Exception:
                continue

        overloaded = []
        for (owner, year, week), tasks in workloads.items():
            if len(tasks) >= 3:
                overloaded.append({
                    "owner": owner,
                    "year": year,
                    "week": week,
                    "count": len(tasks),
                    "tasks": [{"id": t.id, "title": t.title, "deadline": t.deadline} for t in tasks],
                    "recommendation": f"Suggest rebalancing: {owner} has {len(tasks)} deadlines in Week {week}."
                })
        return overloaded
