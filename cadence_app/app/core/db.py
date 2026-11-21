import sqlite3
import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "cadence.db")

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # Meetings table
    c.execute("""
    CREATE TABLE IF NOT EXISTS meetings (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        meeting_date TEXT NOT NULL,
        transcript_raw TEXT NOT NULL,
        source TEXT DEFAULT 'text',
        created_at TEXT NOT NULL
    )
    """)

    # Cross-meeting Decisions Memory table
    c.execute("""
    CREATE TABLE IF NOT EXISTS decisions_memory (
        id TEXT PRIMARY KEY,
        meeting_id TEXT,
        meeting_title TEXT NOT NULL,
        meeting_date TEXT NOT NULL,
        text TEXT NOT NULL,
        owner TEXT NOT NULL,
        topic TEXT,
        topic_value TEXT,
        quote TEXT,
        is_superseded INTEGER DEFAULT 0,
        superseded_by TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (meeting_id) REFERENCES meetings(id)
    )
    """)

    # Extracted Items Stage (Prior to confirmation)
    c.execute("""
    CREATE TABLE IF NOT EXISTS extracted_items (
        id TEXT PRIMARY KEY,
        meeting_id TEXT NOT NULL,
        kind TEXT NOT NULL, -- 'dec' or 'act'
        text TEXT NOT NULL,
        owner TEXT NOT NULL,
        deadline TEXT,
        topic TEXT,
        topic_value TEXT,
        quote TEXT,
        speaker TEXT,
        confidence REAL DEFAULT 0.85,
        is_selected INTEGER DEFAULT 1,
        is_confirmed INTEGER DEFAULT 0,
        FOREIGN KEY (meeting_id) REFERENCES meetings(id)
    )
    """)

    # Conflicts Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS conflicts (
        conflict_id TEXT PRIMARY KEY,
        meeting_id TEXT NOT NULL,
        extracted_item_id TEXT NOT NULL,
        topic TEXT NOT NULL,
        severity TEXT NOT NULL, -- 'hard', 'soft', 'dup'
        new_text TEXT NOT NULL,
        new_owner TEXT NOT NULL,
        new_deadline TEXT,
        existing_memory_id TEXT NOT NULL,
        existing_meeting_title TEXT,
        existing_meeting_date TEXT,
        existing_text TEXT NOT NULL,
        existing_owner TEXT NOT NULL,
        reason TEXT NOT NULL,
        resolution TEXT, -- 'keep_new', 'keep_existing', 'both', 'dismissed'
        resolved_at TEXT,
        FOREIGN KEY (meeting_id) REFERENCES meetings(id),
        FOREIGN KEY (extracted_item_id) REFERENCES extracted_items(id),
        FOREIGN KEY (existing_memory_id) REFERENCES decisions_memory(id)
    )
    """)

    # Tracker Tasks Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        external_ticket TEXT NOT NULL UNIQUE,
        meeting_id TEXT NOT NULL,
        tracker TEXT NOT NULL,
        title TEXT NOT NULL,
        owner TEXT NOT NULL,
        deadline TEXT,
        status TEXT DEFAULT 'open', -- 'open', 'in_progress', 'done'
        created_at TEXT NOT NULL,
        updated_at TEXT,
        FOREIGN KEY (meeting_id) REFERENCES meetings(id)
    )
    """)

    # Reminders Queue & Log Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS reminders (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        external_ticket TEXT NOT NULL,
        recipient TEXT NOT NULL,
        title TEXT NOT NULL,
        deadline TEXT NOT NULL,
        scheduled_date TEXT NOT NULL,
        sent INTEGER DEFAULT 0,
        sent_at TEXT,
        message TEXT NOT NULL,
        FOREIGN KEY (task_id) REFERENCES tasks(id)
    )
    """)

    # Audit Logs
    c.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        description TEXT NOT NULL,
        details_json TEXT,
        created_at TEXT NOT NULL
    )
    """)

    conn.commit()

    # Seed baseline cross-meeting memory if empty
    c.execute("SELECT COUNT(*) FROM decisions_memory")
    count = c.fetchone()[0]
    if count == 0:
        seed_baseline_memory(conn)
    
    conn.close()

def seed_baseline_memory(conn):
    c = conn.cursor()
    now = datetime.now().isoformat()
    baseline = [
        ("mem-101", "m-prev-1", "Architecture Review", "Jan 15", "Use PostgreSQL for the primary transactional database", "Arjun", "database", "postgres", "Arjun: We will stick to PostgreSQL for all core persistence.", 0, None, now),
        ("mem-102", "m-prev-2", "Roadmap Planning Q1", "Jan 28", "Product launch date scheduled for April 2", "Priya", "launch", "2026-04-02", "Priya: Let us lock in the target launch date as April 2.", 0, None, now),
        ("mem-103", "m-prev-3", "Go-To-Market & Pricing", "Feb 05", "Adopt tiered seat-based pricing model at $29/seat/month", "Sana", "pricing", "29_tier", "Sana: The consensus is $29 per user seat monthly.", 0, None, now),
        ("mem-104", "m-prev-4", "Internal Ops & Tooling", "Feb 10", "All cross-team async updates happen in Discord channels", "Ravi", "comms", "discord", "Ravi: Discord is chosen over Slack for internal updates.", 0, None, now),
        ("mem-105", "m-prev-5", "Mobile Strategy Sync", "Feb 14", "Flutter selected as the cross-platform mobile framework", "Arjun", "mobile_stack", "flutter", "Arjun: We decided on Flutter for Android and iOS apps.", 0, None, now)
    ]
    c.executemany("""
    INSERT INTO decisions_memory (id, meeting_id, meeting_title, meeting_date, text, owner, topic, topic_value, quote, is_superseded, superseded_by, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, baseline)
    conn.commit()
