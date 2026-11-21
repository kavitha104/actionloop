import pytest
from backend.database import SessionLocal, Base, engine
from backend.models.domain import Decision, Meeting, ActionItem, Conflict, AuditLog
from backend.services.conflict_service import ConflictService
from seed import seed_database

@pytest.fixture(autouse=True)
def setup_seed():
    seed_database()

def test_conflict_detection_stripe_vs_paypal():
    db = SessionLocal()
    try:
        # Check active Stripe decision exists
        stripe_dec = db.query(Decision).filter(
            Decision.status == "active",
            Decision.topic == "payments"
        ).first()
        assert stripe_dec is not None
        assert "stripe" in stripe_dec.statement.lower()

        # Simulate candidate decision from Meeting 3: "Switch to PayPal for payments"
        conflict_result = ConflictService.evaluate_decision_conflict(
            db=db,
            new_statement="Switch to PayPal for all payment processing",
            topic="payments",
            made_by="Priya Sharma",
            evidence_quote="Priya: Okay, let's switch to PayPal for all payment processing.",
            meeting_id=99  # distinct meeting
        )

        assert conflict_result is not None, "Conflict should be flagged against Stripe decision"
        assert conflict_result["conflict_type"] == "contradiction"
        assert conflict_result["severity"] in ["critical", "hard", "warning"]
        assert conflict_result["existing_decision_id"] == stripe_dec.id
        assert "stripe" in conflict_result["explanation"].lower() or "paypal" in conflict_result["explanation"].lower()
    finally:
        db.close()

def test_conflict_resolution_supersede_lineage():
    db = SessionLocal()
    try:
        stripe_dec = db.query(Decision).filter(Decision.topic == "payments").first()
        
        # Create candidate new decision in DB
        paypal_dec = Decision(
            meeting_id=stripe_dec.meeting_id + 1,
            statement="Switch to PayPal for all payment processing",
            topic="payments",
            made_by="Priya Sharma",
            status="conflicted"
        )
        db.add(paypal_dec)
        db.flush()

        # Create Conflict record
        conf = Conflict(
            new_item_type="decision",
            new_item_id=paypal_dec.id,
            existing_decision_id=stripe_dec.id,
            conflict_type="contradiction",
            severity="critical",
            explanation="Contradicts Stripe decision",
            resolution="pending"
        )
        db.add(conf)
        db.commit()

        # Resolve with supersede_old
        resolved = ConflictService.resolve_conflict(
            db=db,
            conflict_id=conf.id,
            resolution="supersede_old",
            resolved_by="Priya Sharma"
        )

        db.refresh(stripe_dec)
        db.refresh(paypal_dec)

        assert resolved.resolution == "supersede_old"
        assert stripe_dec.status == "superseded", "Old Stripe decision must be marked superseded"
        assert paypal_dec.status == "active", "New PayPal decision must become active"
        assert paypal_dec.supersedes_id == stripe_dec.id, "Lineage link must point to old decision"

        # Check Audit Log
        audit = db.query(AuditLog).filter(AuditLog.entity == "Conflict", AuditLog.entity_id == conf.id).first()
        assert audit is not None
        assert "supersede_old" in audit.action
    finally:
        db.close()
