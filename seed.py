import sys
import os
import datetime

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath("."))

from backend.database import Base, engine, SessionLocal
from backend.models.domain import (
    Meeting, Utterance, Decision, ActionItem, LooseEnd, Conflict, Person, OutboxItem, AuditLog
)

def seed_database():
    print("Initializing ActionLoop database schema...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 1. Seed People
        people_data = [
            {"name": "Priya Sharma", "email": "priya@example.com", "aliases": ["Priya", "priyasharma", "PS"], "slack_handle": "@priya"},
            {"name": "Arjun Mehta", "email": "arjun@example.com", "aliases": ["Arjun", "arjunm", "AM"], "slack_handle": "@arjun"},
            {"name": "Sana Patel", "email": "sana@example.com", "aliases": ["Sana", "sanap", "SP"], "slack_handle": "@sana"},
            {"name": "Ravi Kumar", "email": "ravi@example.com", "aliases": ["Ravi", "ravik", "RK"], "slack_handle": "@ravi"},
            {"name": "Maya Lin", "email": "maya@example.com", "aliases": ["Maya", "mayal", "ML"], "slack_handle": "@maya"},
        ]

        for p in people_data:
            person = Person(
                name=p["name"],
                email=p["email"],
                aliases=p["aliases"],
                slack_handle=p["slack_handle"],
                auto_remind=True
            )
            db.add(person)
        db.commit()
        print("Seeded 5 team members.")

        # 2. Meeting 1 (Week 1: Jan 15, 2026 - Architecture & Payments Kickoff)
        m1_raw = (
            "Priya: Welcome everyone. Let's lock in our payment architecture for the launch.\n"
            "Arjun: I evaluated Stripe and Braintree. Stripe gives us the fastest path to PCI compliance.\n"
            "Priya: Agreed. We decided to use Stripe for payments for the initial rollout.\n"
            "Sana: That works well for marketing too. When are we targeting launch?\n"
            "Priya: We decided to launch on March 15.\n"
            "Arjun: I will finalize the Stripe webhook integration and customer schema by Feb 20.\n"
            "Ravi: Ravi to provision the production Redis cluster and VPC peering by Feb 18.\n"
            "Maya: I will deliver the checkout UI component library by Feb 10."
        )

        m1 = Meeting(
            title="Sprint Kickoff & Payment Architecture",
            date="2026-01-15",
            project="Core Platform",
            participants=["Priya Sharma", "Arjun Mehta", "Sana Patel", "Ravi Kumar", "Maya Lin"],
            raw_transcript=m1_raw,
            status="reviewed"
        )
        db.add(m1)
        db.flush()

        # Utterances for M1
        u1_1 = Utterance(meeting_id=m1.id, speaker="Priya Sharma", text="Welcome everyone. Let's lock in our payment architecture for the launch.", order_index=0)
        u1_2 = Utterance(meeting_id=m1.id, speaker="Arjun Mehta", text="I evaluated Stripe and Braintree. Stripe gives us the fastest path to PCI compliance.", order_index=1)
        u1_3 = Utterance(meeting_id=m1.id, speaker="Priya Sharma", text="Agreed. We decided to use Stripe for payments for the initial rollout.", order_index=2)
        u1_4 = Utterance(meeting_id=m1.id, speaker="Sana Patel", text="That works well for marketing too. When are we targeting launch?", order_index=3)
        u1_5 = Utterance(meeting_id=m1.id, speaker="Priya Sharma", text="We decided to launch on March 15.", order_index=4)
        u1_6 = Utterance(meeting_id=m1.id, speaker="Arjun Mehta", text="I will finalize the Stripe webhook integration and customer schema by Feb 20.", order_index=5)
        u1_7 = Utterance(meeting_id=m1.id, speaker="Ravi Kumar", text="Ravi to provision the production Redis cluster and VPC peering by Feb 18.", order_index=6)
        u1_8 = Utterance(meeting_id=m1.id, speaker="Maya Lin", text="I will deliver the checkout UI component library by Feb 10.", order_index=7)
        db.add_all([u1_1, u1_2, u1_3, u1_4, u1_5, u1_6, u1_7, u1_8])
        db.flush()

        # Decisions for M1
        d1 = Decision(
            meeting_id=m1.id,
            statement="Use Stripe for payments for the initial rollout",
            rationale="Fastest path to PCI compliance and cleanest developer API",
            topic="payments",
            made_by="Priya Sharma",
            status="active",
            source_utterance_ids=[u1_3.id]
        )
        d2 = Decision(
            meeting_id=m1.id,
            statement="Launch target is March 15",
            rationale="Aligned with Q1 marketing cycle",
            topic="launch",
            made_by="Priya Sharma",
            status="active",
            source_utterance_ids=[u1_5.id]
        )
        db.add_all([d1, d2])
        db.flush()

        # Action Items for M1 (Approved & posted to tracker)
        a1 = ActionItem(
            meeting_id=m1.id,
            title="Finalize Stripe webhook integration and customer schema",
            description="Integrate webhooks, error handling, and test with Stripe test keys. Evidence: 'I will finalize the Stripe webhook integration and customer schema by Feb 20.'",
            owner="Arjun Mehta",
            needs_owner=False,
            deadline="2026-02-20",
            raw_deadline_phrase="by Feb 20",
            priority="high",
            status="posted",
            confidence=0.96,
            source_utterance_ids=[u1_6.id],
            tracker_ref="MOCK-101",
            reminder_state="scheduled"
        )
        a2 = ActionItem(
            meeting_id=m1.id,
            title="Provision production Redis cluster and VPC peering",
            description="Set up secure AWS VPC peering and Redis cluster for session cache. Evidence: 'Ravi to provision the production Redis cluster and VPC peering by Feb 18.'",
            owner="Ravi Kumar",
            needs_owner=False,
            deadline="2026-02-18",
            raw_deadline_phrase="by Feb 18",
            priority="medium",
            status="done",
            confidence=0.94,
            source_utterance_ids=[u1_7.id],
            tracker_ref="MOCK-102",
            reminder_state="done"
        )
        a3 = ActionItem(
            meeting_id=m1.id,
            title="Deliver checkout UI component library",
            description="Figma tokens to React components for checkout form. Evidence: 'I will deliver the checkout UI component library by Feb 10.'",
            owner="Maya Lin",
            needs_owner=False,
            deadline="2026-02-10",
            raw_deadline_phrase="by Feb 10",
            priority="high",
            status="done",
            confidence=0.95,
            source_utterance_ids=[u1_8.id],
            tracker_ref="MOCK-103",
            reminder_state="done"
        )
        db.add_all([a1, a2, a3])
        db.flush()

        # Outbox item for M1
        o1 = OutboxItem(
            type="task",
            payload={"task_id": a1.id, "title": a1.title, "owner": a1.owner, "deadline": a1.deadline},
            status="sent",
            approved_by="Priya Sharma",
            destination="tracker",
            external_ref="MOCK-101"
        )
        db.add(o1)

        # 3. Meeting 2 (Week 2: Jan 22, 2026 - Scope Realignment & Beta Phase)
        m2_raw = (
            "Priya: Team, after reviewing the security audit results, we need more testing runway.\n"
            "Sana: Customers are asking for an early preview before full GA.\n"
            "Priya: We decided to move the launch date to April 1 and introduce a 2-week closed beta.\n"
            "Arjun: Understood. That gives us buffer for load testing.\n"
            "Sana: I will draft the beta invite program criteria by Feb 28.\n"
            "Arjun: I will implement the feature flags for closed beta access by Mar 5.\n"
            "Ravi: Someone should check the AWS egress cost estimates for beta."
        )

        m2 = Meeting(
            title="Roadmap Realignment & Beta Plan",
            date="2026-01-22",
            project="Core Platform",
            participants=["Priya Sharma", "Arjun Mehta", "Sana Patel", "Ravi Kumar"],
            raw_transcript=m2_raw,
            status="reviewed"
        )
        db.add(m2)
        db.flush()

        u2_1 = Utterance(meeting_id=m2.id, speaker="Priya Sharma", text="Team, after reviewing the security audit results, we need more testing runway.", order_index=0)
        u2_2 = Utterance(meeting_id=m2.id, speaker="Sana Patel", text="Customers are asking for an early preview before full GA.", order_index=1)
        u2_3 = Utterance(meeting_id=m2.id, speaker="Priya Sharma", text="We decided to move the launch date to April 1 and introduce a 2-week closed beta.", order_index=2)
        u2_4 = Utterance(meeting_id=m2.id, speaker="Arjun Mehta", text="Understood. That gives us buffer for load testing.", order_index=3)
        u2_5 = Utterance(meeting_id=m2.id, speaker="Sana Patel", text="I will draft the beta invite program criteria by Feb 28.", order_index=4)
        u2_6 = Utterance(meeting_id=m2.id, speaker="Arjun Mehta", text="I will implement the feature flags for closed beta access by Mar 5.", order_index=5)
        u2_7 = Utterance(meeting_id=m2.id, speaker="Ravi Kumar", text="Someone should check the AWS egress cost estimates for beta.", order_index=6)
        db.add_all([u2_1, u2_2, u2_3, u2_4, u2_5, u2_6, u2_7])
        db.flush()

        # Decision in M2 supersedes d2 (March 15 launch)
        d2.status = "superseded"
        db.add(d2)

        d3 = Decision(
            meeting_id=m2.id,
            statement="Move launch date to April 1 and add 2-week closed beta phase",
            rationale="Runway required for security testing and customer preview",
            topic="launch",
            made_by="Priya Sharma",
            status="active",
            supersedes_id=d2.id,
            source_utterance_ids=[u2_3.id]
        )
        db.add(d3)
        db.flush()

        # Action items for M2
        a4 = ActionItem(
            meeting_id=m2.id,
            title="Draft beta invite program criteria",
            description="Define qualification for first 50 beta organizations. Evidence: 'I will draft the beta invite program criteria by Feb 28.'",
            owner="Sana Patel",
            needs_owner=False,
            deadline="2026-02-28",
            raw_deadline_phrase="by Feb 28",
            priority="high",
            status="posted",
            confidence=0.95,
            source_utterance_ids=[u2_5.id],
            tracker_ref="MOCK-104",
            reminder_state="scheduled"
        )
        a5 = ActionItem(
            meeting_id=m2.id,
            title="Implement feature flags for closed beta access",
            description="Set up tenant gating via LaunchDarkly or Unleash. Evidence: 'I will implement the feature flags for closed beta access by Mar 5.'",
            owner="Arjun Mehta",
            needs_owner=False,
            deadline="2026-03-05",
            raw_deadline_phrase="by Mar 5",
            priority="medium",
            status="posted",
            confidence=0.92,
            source_utterance_ids=[u2_6.id],
            tracker_ref="MOCK-105",
            reminder_state="scheduled"
        )
        db.add_all([a4, a5])

        # Loose end in M2
        le1 = LooseEnd(
            meeting_id=m2.id,
            text="Check AWS egress cost estimates for beta",
            source_utterance_ids=[u2_7.id],
            status="open"
        )
        db.add(le1)

        # Audit logs
        log1 = AuditLog(
            actor="Priya Sharma",
            action="supersede_decision",
            entity="Decision",
            entity_id=d2.id,
            before_json='{"status": "active", "date": "March 15"}',
            after_json='{"status": "superseded", "superseded_by": "April 1 launch + beta"}'
        )
        log2 = AuditLog(
            actor="System",
            action="post_task",
            entity="ActionItem",
            entity_id=a1.id,
            before_json='{"status": "approved"}',
            after_json='{"status": "posted", "tracker_ref": "MOCK-101"}'
        )
        db.add_all([log1, log2])

        db.commit()
        print("Successfully seeded Meetings 1 & 2, active decisions, superseded lineage, action items, and loose ends.")
        print("Ready for live demo meeting ingestion (Meeting 3).")

    except Exception as e:
        db.rollback()
        print(f"Error during seeding: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
