import re
import uuid
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from app.models.schemas import ExtractedItem, ItemKind

# Known topic extractors to detect semantic domain & specific value
TOPIC_RULES = [
    {
        "topic": "launch",
        "patterns": [
            r"launch(?:ing|ed)?\s+(?:on|date|for|by)?\s*([A-Za-z]+ \d{1,2}|\d{4}-\d{2}-\d{2})",
            r"release(?:d)?\s+(?:on|date|for|by)?\s*([A-Za-z]+ \d{1,2}|\d{4}-\d{2}-\d{2})",
            r"ship(?:ping)?\s+(?:on|date|for|by)?\s*([A-Za-z]+ \d{1,2}|\d{4}-\d{2}-\d{2})"
        ]
    },
    {
        "topic": "database",
        "patterns": [
            r"(?:use|choose|chosen|picked|switch to|migrate to|stick to)\s+(postgres|postgresql|mongodb|mysql|sqlite|dynamodb|cassandra|redis|planetscale)",
            r"(postgres|postgresql|mongodb|mysql|sqlite|dynamodb)\s+(?:as|for)\s+(?:the\s+)?(?:main|primary|core)?\s*database"
        ]
    },
    {
        "topic": "pricing",
        "patterns": [
            r"\$(\d+(?:\.\d+)?)\s*(?:\/|\s*per\s*)?(?:user|seat|month|mo)?",
            r"(?:price|pricing|tier)\s*(?:at|of|is)?\s*\$?(\d+(?:\.\d+)?)",
            r"(usage[ -]based|flat[ -]rate|freemium|seat[ -]based)"
        ]
    },
    {
        "topic": "comms",
        "patterns": [
            r"(?:use|switch to|on|migrate to)\s+(slack|discord|teams|mattermost|email)",
            r"(slack|discord|teams)\s+for\s+(?:internal\s+)?(?:comms|updates|communication)"
        ]
    },
    {
        "topic": "mobile_stack",
        "patterns": [
            r"(?:use|build with|choose)\s+(flutter|react native|swift|kotlin|native)",
            r"(flutter|react native|swift|kotlin)\s+for\s+(?:mobile|apps)"
        ]
    }
]

# Cue phrases indicating a team agreement / decision
DECISION_CUES = [
    r"\bwe decided\b",
    r"\bwe agreed\b",
    r"\bconsensus is\b",
    r"\blet'?s go with\b",
    r"\blet'?s lock in\b",
    r"\bdecision is\b",
    r"\bmoving forward with\b",
    r"\bwe will use\b",
    r"\bwe will stick with\b",
    r"\bwe are switching to\b",
    r"\bsettled on\b"
]

# Cue phrases indicating an individual action commitment / task assignment
ACTION_CUES = [
    r"\bi will\b",
    r"\bi'll\b",
    r"\bcan you\b",
    r"\bplease take\b",
    r"\bassigned to\b",
    r"\btake the lead on\b",
    r"\bwill handle\b",
    r"\bwill build\b",
    r"\bwill draft\b",
    r"\bwill prepare\b",
    r"\bwill set up\b",
    r"\bwill follow up\b",
    r"\baction item\b"
]

DEADLINE_CUES = [
    r"(?:by|before|due(?:\s+date)?(?:\s+is)?|until)\s+([A-Z][a-z]{2,8}\s+\d{1,2}(?:st|nd|rd|th)?|\d{4}-\d{2}-\d{2}|tomorrow|next\s+[A-Za-z]+|Friday|Monday|Tuesday|Wednesday|Thursday|end of week|EOD)",
    r"deadline\s*(?:is)?\s*([A-Z][a-z]{2,8}\s+\d{1,2}|\d{4}-\d{2}-\d{2})"
]

class ExtractionService:
    @staticmethod
    def parse_speakers_and_lines(transcript: str) -> List[Dict[str, str]]:
        """
        Parses transcripts with speaker attribution.
        Accepts formats like:
        - Priya: We decided to launch on March 14.
        - [Arjun] I will migrate the database schemas by Friday.
        - Ravi (10:14 AM): We agreed to use Slack for notifications.
        """
        lines = transcript.strip().split("\n")
        parsed = []
        speaker_regex = re.compile(r"^(?:\[([^\]]+)\]|([A-Za-z0-9_\s\.\-]+?)(?:\s*\([^)]*\))?)\s*:\s*(.*)$")

        current_speaker = "Unknown"
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            match = speaker_regex.match(line_str)
            if match:
                s1, s2, content = match.groups()
                speaker = (s1 or s2).strip()
                current_speaker = speaker
                parsed.append({
                    "speaker": speaker,
                    "content": content.strip(),
                    "raw": line_str
                })
            else:
                # Continuation line
                parsed.append({
                    "speaker": current_speaker,
                    "content": line_str,
                    "raw": line_str
                })
        return parsed

    @classmethod
    def extract_topic_and_value(cls, text: str) -> Tuple[Optional[str], Optional[str]]:
        for t in TOPIC_RULES:
            for pat in t["patterns"]:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    val = m.group(1).lower().strip()
                    # Normalization
                    if val in ["postgresql", "postgres"]:
                        val = "postgres"
                    return t["topic"], val
        return None, None

    @classmethod
    def extract_deadline(cls, text: str) -> Optional[str]:
        for pat in DEADLINE_CUES:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    @classmethod
    def extract_items_from_transcript(cls, transcript: str) -> List[ExtractedItem]:
        parsed_lines = cls.parse_speakers_and_lines(transcript)
        extracted: List[ExtractedItem] = []

        for row in parsed_lines:
            text = row["content"]
            speaker = row["speaker"]
            raw_quote = row["raw"]

            # Check for decisions
            is_decision = any(re.search(pat, text, re.IGNORECASE) for pat in DECISION_CUES)
            is_action = any(re.search(pat, text, re.IGNORECASE) for pat in ACTION_CUES)

            topic, topic_val = cls.extract_topic_and_value(text)
            deadline = cls.extract_deadline(text)

            # Determine Owner
            owner = speaker if speaker != "Unknown" else "Unassigned"
            # Look for assigned name in text (e.g. "Arjun will handle...")
            assigned_match = re.search(r"\b([A-Z][a-z]+)\s+will\b", text)
            if assigned_match:
                candidate = assigned_match.group(1)
                if candidate.lower() not in ["we", "it", "this", "they"]:
                    owner = candidate

            if is_decision:
                # Clean up decision title
                clean_title = text
                for cue in DECISION_CUES:
                    clean_title = re.sub(cue, "", clean_title, flags=re.IGNORECASE)
                clean_title = clean_title.strip(" :,.-")
                if len(clean_title) > 0:
                    clean_title = clean_title[0].upper() + clean_title[1:]

                confidence = 0.92 if topic else 0.85

                extracted.append(ExtractedItem(
                    id=f"ext-{uuid.uuid4().hex[:8]}",
                    kind=ItemKind.DECISION,
                    text=clean_title if len(clean_title) > 10 else text,
                    owner=owner,
                    deadline=deadline,
                    topic=topic,
                    topic_value=topic_val,
                    quote=raw_quote,
                    speaker=speaker,
                    confidence=confidence,
                    is_selected=True
                ))

            elif is_action or deadline:
                clean_act = text
                for cue in ACTION_CUES:
                    clean_act = re.sub(cue, "", clean_act, flags=re.IGNORECASE)
                clean_act = clean_act.strip(" :,.-")
                if len(clean_act) > 0:
                    clean_act = clean_act[0].upper() + clean_act[1:]

                confidence = 0.88 if deadline else 0.72

                extracted.append(ExtractedItem(
                    id=f"ext-{uuid.uuid4().hex[:8]}",
                    kind=ItemKind.ACTION,
                    text=clean_act if len(clean_act) > 10 else text,
                    owner=owner,
                    deadline=deadline,
                    topic=topic,
                    topic_value=topic_val,
                    quote=raw_quote,
                    speaker=speaker,
                    confidence=confidence,
                    is_selected=True
                ))

        # Fallback: if empty or raw sentences without standard cues, extract key sentences
        if not extracted and parsed_lines:
            for row in parsed_lines:
                if len(row["content"]) > 15:
                    extracted.append(ExtractedItem(
                        id=f"ext-{uuid.uuid4().hex[:8]}",
                        kind=ItemKind.ACTION,
                        text=row["content"],
                        owner=row["speaker"],
                        deadline=cls.extract_deadline(row["content"]),
                        topic=None,
                        topic_value=None,
                        quote=row["raw"],
                        speaker=row["speaker"],
                        confidence=0.65,
                        is_selected=True
                    ))

        return extracted
