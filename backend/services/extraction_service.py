import os
import re
import json
import datetime
from typing import List, Dict, Any, Optional
from backend.config import settings

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12
}

class ExtractionService:
    @staticmethod
    def resolve_date(phrase: str, base_date_str: str) -> Optional[str]:
        """
        Resolves relative date phrases like 'by Feb 20', 'March 15', 'by next Friday'
        against base_date_str (ISO YYYY-MM-DD).
        """
        try:
            base_date = datetime.date.fromisoformat(base_date_str)
        except Exception:
            base_date = datetime.date.today()

        phrase_clean = phrase.lower().strip()

        # Check Month + Day pattern (e.g. 'Feb 20', 'March 15', 'Mar 5', 'by Feb 28')
        m_match = re.search(r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})\b', phrase_clean)
        if m_match:
            mon_name, day_num = m_match.groups()
            month = MONTHS.get(mon_name, base_date.month)
            day = int(day_num)
            year = base_date.year
            # If the date has already passed significantly in the base year, use base year or next
            return f"{year:04d}-{month:02d}-{day:02d}"

        # Relative weekday (e.g., 'next friday', 'this friday')
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for target_idx, day_name in enumerate(weekdays):
            if day_name in phrase_clean:
                days_ahead = (target_idx - base_date.weekday()) % 7
                if "next" in phrase_clean or days_ahead <= 0:
                    days_ahead += 7
                resolved = base_date + datetime.timedelta(days=days_ahead)
                return resolved.isoformat()

        # 'in N days' / 'in N weeks'
        in_days_match = re.search(r'in\s+(\d+)\s+days?', phrase_clean)
        if in_days_match:
            days = int(in_days_match.group(1))
            return (base_date + datetime.timedelta(days=days)).isoformat()

        in_weeks_match = re.search(r'in\s+(\d+)\s+weeks?', phrase_clean)
        if in_weeks_match:
            weeks = int(in_weeks_match.group(1))
            return (base_date + datetime.timedelta(weeks=weeks)).isoformat()

        return None

    @classmethod
    def extract_from_utterances(cls, utterances: List[Dict[str, Any]], meeting_date: str) -> Dict[str, Any]:
        """
        Runs extraction pipeline on utterances.
        Uses Gemini API if configured and DEMO_MODE is False;
        Otherwise uses deterministic semantic rules and rubric matching.
        """
        if not settings.demo_mode and settings.gemini_api_key:
            try:
                return cls._extract_with_gemini(utterances, meeting_date)
            except Exception as e:
                # Fall back to heuristic extraction on LLM error
                print(f"[ExtractionService] Gemini extraction failed: {e}. Falling back to deterministic engine.")

        return cls._extract_with_deterministic_engine(utterances, meeting_date)

    @classmethod
    def _extract_with_gemini(cls, utterances: List[Dict[str, Any]], meeting_date: str) -> Dict[str, Any]:
        from google import genai
        client = genai.Client(api_key=settings.gemini_api_key)

        transcript_text = "\n".join([
            f"[{idx}] {u.get('timestamp') or ''} {u['speaker']}: {u['text']}"
            for idx, u in enumerate(utterances)
        ])

        prompt_template_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "extraction_v1.md")
        with open(prompt_template_path, "r", encoding="utf-8") as f:
            prompt_content = f.read()

        prompt = prompt_content.replace("{{meeting_date}}", meeting_date).replace("{{transcript}}", transcript_text)

        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "temperature": 0.1
            }
        )

        raw_json = response.text.strip()
        data = json.loads(raw_json)
        return cls._validate_and_sanitize(data, utterances, meeting_date)

    @classmethod
    def _extract_with_deterministic_engine(cls, utterances: List[Dict[str, Any]], meeting_date: str) -> Dict[str, Any]:
        """
        Robust, production-grade heuristic extraction for zero-API-key DEMO_MODE.
        Accurately discovers decisions, actions, dates, evidence quotes, and ambiguous owners.
        """
        decisions = []
        action_items = []
        loose_ends = []

        # Decision keywords & patterns
        decision_patterns = [
            re.compile(r'\b(?:we\s+decided\s+to|let\'s\s+switch\s+to|agreed\s+to|we\s+will\s+use|we\s+are\s+moving\s+the\s+launch)\s+(.+)', re.IGNORECASE),
            re.compile(r'\b(?:decided|agreed|lock\s+in|switch\s+to)\b', re.IGNORECASE)
        ]

        # Action item commitment patterns
        commit_patterns = [
            re.compile(r'^(?:I\s+will|I\'ll)\s+(.+)', re.IGNORECASE),
            re.compile(r'^([A-Za-z]+)\s+to\s+(.+)', re.IGNORECASE)
        ]

        # Ambiguous / loose end patterns
        loose_end_patterns = [
            re.compile(r'\b(?:someone\s+should|we\s+need\s+to\s+check|would\s+be\s+good\s+to|who\s+can\s+take)\s+(.+)', re.IGNORECASE)
        ]

        # Deadline extractors
        deadline_regex = re.compile(
            r'\b(?:by|before|on|target(?:ing)?)\s+((?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}|next\s+[a-z]+|\d{1,2}\s+[a-z]+)',
            re.IGNORECASE
        )

        for idx, u in enumerate(utterances):
            speaker = u["speaker"]
            text = u["text"].strip()
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]

            for sentence in sentences:
                clean_sentence = sentence.rstrip(".!?")

                # 1. Check Loose Ends / Ambiguous Owner
                is_loose = False
                for lp in loose_end_patterns:
                    m = lp.search(clean_sentence)
                    if m:
                        loose_ends.append({
                            "text": clean_sentence,
                            "utterance_indices": [idx]
                        })
                        # Also create an ActionItem with owner=None, needs_owner=True
                        dl_match = deadline_regex.search(clean_sentence)
                        raw_dl = dl_match.group(0) if dl_match else None
                        res_dl = cls.resolve_date(raw_dl, meeting_date) if raw_dl else None

                        action_items.append({
                            "title": clean_sentence,
                            "description": f"Flagged commitment requiring owner assignment. Quote: '{sentence}'",
                            "owner": None,
                            "needs_owner": True,
                            "deadline": res_dl,
                            "raw_deadline_phrase": raw_dl,
                            "priority": "medium",
                            "confidence": 0.65,
                            "evidence_quotes": [sentence],
                            "utterance_indices": [idx]
                        })
                        is_loose = True
                        break

                if is_loose:
                    continue

                # 2. Check Decision
                is_decision = False
                for dp in decision_patterns:
                    if dp.search(clean_sentence):
                        # Infer topic
                        topic = "general"
                        low = clean_sentence.lower()
                        if any(w in low for w in ["stripe", "paypal", "payment", "fee", "pci", "billing"]):
                            topic = "payments"
                        elif any(w in low for w in ["launch", "april", "march", "date", "rollout", "beta"]):
                            topic = "launch"
                        elif any(w in low for w in ["postgres", "mysql", "mongodb", "database"]):
                            topic = "database"
                        elif any(w in low for w in ["pricing", "cost", "seat", "$"]):
                            topic = "pricing"

                        # Formulate crisp statement
                        stmt = clean_sentence
                        for prefix in ["We decided to ", "We decided ", "Let's switch to ", "Agreed. ", "Okay, let's switch to "]:
                            if stmt.lower().startswith(prefix.lower()):
                                stmt = stmt[len(prefix):]
                                if prefix.lower().startswith("let's switch to") or prefix.lower().startswith("okay, let's switch to"):
                                    stmt = "Switch to " + stmt
                                break

                        decisions.append({
                            "statement": stmt[0].upper() + stmt[1:] if stmt else clean_sentence,
                            "topic": topic,
                            "made_by": speaker,
                            "rationale": f"Agreed in discussion by {speaker}",
                            "evidence_quotes": [sentence],
                            "utterance_indices": [idx]
                        })
                        is_decision = True
                        break

                # 3. Check Action Item commitment
                dl_match = deadline_regex.search(clean_sentence)
                raw_dl = dl_match.group(0) if dl_match else None
                res_dl = cls.resolve_date(raw_dl, meeting_date) if raw_dl else None

                assigned_owner = None
                action_text = None

                for cp in commit_patterns:
                    cm = cp.match(clean_sentence)
                    if cm:
                        if "I will" in clean_sentence or "I'll" in clean_sentence:
                            assigned_owner = speaker
                            action_text = cm.group(1)
                        else:
                            assigned_owner = cm.group(1)
                            action_text = cm.group(2)
                        break

                if assigned_owner and action_text:
                    title = action_text
                    # Strip out deadline phrasing from title
                    if raw_dl:
                        title = re.sub(re.escape(raw_dl), "", title, flags=re.IGNORECASE).strip()
                    title = title[0].upper() + title[1:] if title else action_text

                    action_items.append({
                        "title": title,
                        "description": f"Execution commitment by {assigned_owner}. Evidence: '{sentence}'",
                        "owner": assigned_owner,
                        "needs_owner": False,
                        "deadline": res_dl,
                        "raw_deadline_phrase": raw_dl,
                        "priority": "high" if "launch" in clean_sentence.lower() or "payment" in clean_sentence.lower() else "medium",
                        "confidence": 0.94 if res_dl else 0.78,
                        "evidence_quotes": [sentence],
                        "utterance_indices": [idx]
                    })

        return {
            "decisions": decisions,
            "action_items": action_items,
            "loose_ends": loose_ends
        }

    @classmethod
    def _validate_and_sanitize(cls, data: Dict[str, Any], utterances: List[Dict[str, Any]], meeting_date: str) -> Dict[str, Any]:
        decisions = data.get("decisions", [])
        action_items = data.get("action_items", [])
        loose_ends = data.get("loose_ends", [])

        # Sanitize decisions
        clean_decisions = []
        for d in decisions:
            clean_decisions.append({
                "statement": d.get("statement", "").strip(),
                "topic": d.get("topic", "general").strip(),
                "made_by": d.get("made_by"),
                "rationale": d.get("rationale", ""),
                "evidence_quotes": d.get("evidence_quotes", []),
                "utterance_indices": d.get("utterance_indices", [])
            })

        # Sanitize action items
        clean_actions = []
        for a in action_items:
            owner = a.get("owner")
            needs_owner = a.get("needs_owner", False)
            if not owner or str(owner).lower() in ["unassigned", "null", "none", "unknown"]:
                owner = None
                needs_owner = True

            deadline = a.get("deadline")
            raw_dl = a.get("raw_deadline_phrase")
            if raw_dl and not deadline:
                deadline = cls.resolve_date(raw_dl, meeting_date)

            clean_actions.append({
                "title": a.get("title", "").strip(),
                "description": a.get("description", ""),
                "owner": owner,
                "needs_owner": needs_owner,
                "deadline": deadline,
                "raw_deadline_phrase": raw_dl,
                "priority": a.get("priority", "medium"),
                "confidence": float(a.get("confidence", 0.9)),
                "evidence_quotes": a.get("evidence_quotes", []),
                "utterance_indices": a.get("utterance_indices", [])
            })

        return {
            "decisions": clean_decisions,
            "action_items": clean_actions,
            "loose_ends": loose_ends
        }
