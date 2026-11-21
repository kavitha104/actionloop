import re
import json
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session
from backend.models.domain import Person

class IngestionService:
    @staticmethod
    def parse_transcript(raw_text: str, speaker_mapping: Optional[Dict[str, str]] = None, db: Optional[Session] = None) -> List[Dict[str, Any]]:
        """
        Parses raw transcript in multiple formats:
        - Plain text: 'Name: Text' or '[00:12:03] Name: Text'
        - WebVTT format (WEBVTT cues)
        - SRT subtitle format
        - JSON array: [{"speaker": "...", "text": "...", "timestamp": "..."}]
        
        Normalizes speakers against Person table and user speaker_mapping.
        """
        raw_text = raw_text.strip()
        if not raw_text:
            return []

        # 1. Check if raw_text is JSON
        if raw_text.startswith("[") and raw_text.endswith("]"):
            try:
                data = json.loads(raw_text)
                if isinstance(data, list) and len(data) > 0 and "text" in data[0]:
                    parsed = []
                    for idx, item in enumerate(data):
                        spk = item.get("speaker") or f"Unknown Speaker {idx+1}"
                        parsed.append({
                            "speaker": spk,
                            "timestamp": item.get("timestamp"),
                            "text": item.get("text", "").strip(),
                            "order_index": idx
                        })
                    return IngestionService._normalize_speakers(parsed, speaker_mapping, db)
            except Exception:
                pass

        # 2. Check if raw_text is WebVTT or SRT
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if any("-->" in line for line in lines[:10]):
            return IngestionService._parse_subtitles(lines, speaker_mapping, db)

        # 3. Standard text lines
        parsed_utterances = []
        unknown_counter = 1
        
        # Regexes for timestamp + speaker patterns:
        # e.g.: "[00:12:03] Priya: text" or "00:12:03 Priya: text" or "Priya: text"
        pattern_with_ts = re.compile(r'^(?:\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s+)?([A-Za-z0-9_\- ]{2,30}?):\s*(.+)$')

        for idx, line in enumerate(lines):
            match = pattern_with_ts.match(line)
            if match:
                ts, spk, txt = match.groups()
                spk = spk.strip()
                txt = txt.strip()
                parsed_utterances.append({
                    "speaker": spk,
                    "timestamp": ts,
                    "text": txt,
                    "order_index": idx
                })
            else:
                # If no speaker colon, use unknown speaker or attach to previous
                if parsed_utterances and not line.startswith("["):
                    # Continuation of previous speaker
                    parsed_utterances[-1]["text"] += " " + line
                else:
                    spk = f"Unknown Speaker {unknown_counter}"
                    unknown_counter += 1
                    parsed_utterances.append({
                        "speaker": spk,
                        "timestamp": None,
                        "text": line,
                        "order_index": idx
                    })

        return IngestionService._normalize_speakers(parsed_utterances, speaker_mapping, db)

    @staticmethod
    def _parse_subtitles(lines: List[str], speaker_mapping: Optional[Dict[str, str]], db: Optional[Session]) -> List[Dict[str, Any]]:
        parsed = []
        current_ts = None
        order = 0
        unknown_counter = 1

        vtt_speaker_pattern = re.compile(r'<v\s+([^>]+)>(.*)</v>')
        colon_pattern = re.compile(r'^([A-Za-z0-9_\- ]{2,30}?):\s*(.+)$')

        for line in lines:
            if line.startswith("WEBVTT") or line.isdigit():
                continue
            if "-->" in line:
                current_ts = line.split("-->")[0].strip()
                continue
            
            # Check vtt speaker tag
            vtt_match = vtt_speaker_pattern.match(line)
            if vtt_match:
                spk, txt = vtt_match.groups()
                parsed.append({
                    "speaker": spk.strip(),
                    "timestamp": current_ts,
                    "text": txt.strip(),
                    "order_index": order
                })
                order += 1
                continue

            colon_match = colon_pattern.match(line)
            if colon_match:
                spk, txt = colon_match.groups()
                parsed.append({
                    "speaker": spk.strip(),
                    "timestamp": current_ts,
                    "text": txt.strip(),
                    "order_index": order
                })
                order += 1
            else:
                spk = f"Unknown Speaker {unknown_counter}"
                unknown_counter += 1
                parsed.append({
                    "speaker": spk,
                    "timestamp": current_ts,
                    "text": line,
                    "order_index": order
                })
                order += 1

        return IngestionService._normalize_speakers(parsed, speaker_mapping, db)

    @staticmethod
    def _normalize_speakers(utterances: List[Dict[str, Any]], speaker_mapping: Optional[Dict[str, str]], db: Optional[Session]) -> List[Dict[str, Any]]:
        mapping = speaker_mapping or {}
        
        # Load known people from DB if available
        known_people = []
        if db:
            known_people = db.query(Person).all()

        alias_lookup = {}
        for p in known_people:
            alias_lookup[p.name.lower()] = p.name
            for alias in p.aliases:
                alias_lookup[alias.lower()] = p.name

        for u in utterances:
            original = u["speaker"].strip()
            
            # Check user explicit mapping first
            if original in mapping:
                u["speaker"] = mapping[original]
                continue

            # Check db alias match
            low = original.lower()
            if low in alias_lookup:
                u["speaker"] = alias_lookup[low]
                continue

            # First name match (e.g. "Priya" -> "Priya Sharma")
            matched = False
            for p in known_people:
                first_name = p.name.split()[0].lower()
                if low == first_name:
                    u["speaker"] = p.name
                    matched = True
                    break
            if matched:
                continue

        return utterances
