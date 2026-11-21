import pytest
from backend.services.ingestion_service import IngestionService

def test_parse_plain_text():
    raw = (
        "Priya: We should review our launch date.\n"
        "Arjun: I agree, let's target March 15."
    )
    result = IngestionService.parse_transcript(raw)
    assert len(result) == 2
    assert result[0]["speaker"] == "Priya"
    assert result[0]["text"] == "We should review our launch date."
    assert result[1]["speaker"] == "Arjun"
    assert result[1]["text"] == "I agree, let's target March 15."

def test_parse_timestamped_text():
    raw = (
        "[00:01:23] Priya: First point.\n"
        "[00:01:45] Arjun: Second point."
    )
    result = IngestionService.parse_transcript(raw)
    assert len(result) == 2
    assert result[0]["timestamp"] == "00:01:23"
    assert result[0]["speaker"] == "Priya"
    assert result[1]["timestamp"] == "00:01:45"
    assert result[1]["speaker"] == "Arjun"

def test_parse_vtt():
    vtt = (
        "WEBVTT\n\n"
        "1\n00:00:01.000 --> 00:00:04.000\n<v Priya>Hello team.</v>\n\n"
        "2\n00:00:05.000 --> 00:00:09.000\n<v Arjun>Hello Priya.</v>"
    )
    result = IngestionService.parse_transcript(vtt)
    assert len(result) == 2
    assert result[0]["speaker"] == "Priya"
    assert result[0]["text"] == "Hello team."

def test_speaker_mapping():
    raw = "Speaker 1: Hello from speaker 1."
    mapping = {"Speaker 1": "Sana Patel"}
    result = IngestionService.parse_transcript(raw, speaker_mapping=mapping)
    assert result[0]["speaker"] == "Sana Patel"
