import os
import pytest
from backend.services.ingestion_service import IngestionService
from backend.services.extraction_service import ExtractionService

def test_extraction_sample_meeting_1():
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_meeting_1.txt")
    with open(fixture_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    utterances = IngestionService.parse_transcript(raw_text)
    assert len(utterances) > 0

    extracted = ExtractionService.extract_from_utterances(utterances, meeting_date="2026-01-15")
    decisions = extracted["decisions"]
    actions = extracted["action_items"]

    # Verify Stripe decision
    stripe_decision = next((d for d in decisions if "stripe" in d["statement"].lower()), None)
    assert stripe_decision is not None, "Stripe decision should be extracted"
    assert stripe_decision["topic"] == "payments"
    assert len(stripe_decision["utterance_indices"]) > 0

    # Verify action items with resolved dates
    arjun_action = next((a for a in actions if a["owner"] == "Arjun" or (a["owner"] and "arjun" in a["owner"].lower())), None)
    assert arjun_action is not None, "Arjun's action item should be extracted"
    assert arjun_action["deadline"] == "2026-02-20"
    assert arjun_action["needs_owner"] is False

def test_ambiguous_owner_no_guess_policy():
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_meeting_3.txt")
    with open(fixture_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    utterances = IngestionService.parse_transcript(raw_text)
    extracted = ExtractionService.extract_from_utterances(utterances, meeting_date="2026-02-05")

    actions = extracted["action_items"]
    # Verify ambiguous item "Someone should review our legal compliance terms..."
    legal_item = next((a for a in actions if "legal" in a["title"].lower() or "compliance" in a["title"].lower()), None)
    assert legal_item is not None, "Legal compliance item should be extracted"
    assert legal_item["owner"] is None, "AI must NEVER fabricate an owner when ambiguous"
    assert legal_item["needs_owner"] is True, "Must flag needs_owner = True"
