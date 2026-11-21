# ⚡ ActionLoop (Cadence) — Meeting-to-Execution Agent

> **Turn meeting transcripts into tracked, human-confirmed execution with cross-meeting memory and automated conflict detection.**

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Online%20%F0%9F%9A%80-brightgreen?style=for-the-badge)](https://actionloop-h6gq.onrender.com)
[![API Documentation](https://img.shields.io/badge/Swagger%20API-Docs-blue?style=for-the-badge)](https://actionloop-h6gq.onrender.com/docs)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)

---

## 🌐 Live Demo & Endpoints

| Resource | URL |
|---|---|
| **🚀 Live Application (UI)** | **[https://actionloop-h6gq.onrender.com](https://actionloop-h6gq.onrender.com)** |
| **📚 Interactive Swagger API Docs** | **[https://actionloop-h6gq.onrender.com/docs](https://actionloop-h6gq.onrender.com/docs)** |
| **❤️ System Health Check** | **[https://actionloop-h6gq.onrender.com/health](https://actionloop-h6gq.onrender.com/health)** |

---

## 🎯 The Problem

Decisions made in meetings get lost in docs, Slack chats, and memory:
1. Action items are forgotten or assigned ambiguously.
2. New meetings make decisions that contradict commitments made weeks earlier.
3. No unified system bridges conversation to tracked execution without human friction.

**ActionLoop is not just a transcript summarizer — it is an active execution engine with cross-meeting memory.**

---

## ✨ Key Features

### 1. 🧠 Cross-Meeting Memory & Conflict Detection (Hero Feature)
* Compares incoming decisions and action items against past meeting records.
* Automatically flags **contradictions, scope changes, owner clashes, and deadline conflicts**.
* Provides clear lineage chains (e.g. *Supersedes Decision from Jan 28*).

### 2. 🛡️ Human Confirmation Gate (Airlock)
* **Zero unapproved external postings:** Nothing is created in issue trackers (Mock / GitHub / Linear) or sent via notifications without explicit user review and approval.
* Enforced at the architecture and adapter levels.

### 3. 🎙️ Speaker-Attributed Ingestion & Extraction
* Ingests plain text, `.vtt`, `.srt`, and JSON formats with speaker attribution.
* Maps participants, resolves relative dates (e.g. *"by next Friday"* into exact ISO dates), and strictly preserves verbatim source evidence quotes.
* Ambiguity flags: never fabricates owners or deadlines.

### 4. 📋 Kanban Execution & Progress Tracking
* Live visual tracker board displaying proposed, approved, posted, and completed tasks.
* Status toggling, deadline countdowns, and source quote click-throughs.

### 5. 📬 Proactive Reminders & Weekly Digests
* Automated reminder scheduler scanning for approaching and overdue deadlines.
* Per-person personalized digests aggregating individual commitments and accomplishments.

---

## 🛠️ Architecture & Tech Stack

```
   ┌───────────────────────────────────────────────┐
   │             Meeting Transcripts               │
   │           (Plain Text, VTT, SRT)              │
   └──────────────────────┬────────────────────────┘
                          │
                          ▼
   ┌───────────────────────────────────────────────┐
   │           Stage A: Ingestion Service          │
   │    Speaker Attribution & Date Normalization   │
   └──────────────────────┬────────────────────────┘
                          │
                          ▼
   ┌───────────────────────────────────────────────┐
   │          Stage B: Extraction Service          │
   │       Decisions, Action Items & Quotes        │
   └──────────────────────┬────────────────────────┘
                          │
                          ▼
   ┌───────────────────────────────────────────────┐
   │       Stage C: Cross-Meeting Memory           │
   │       Vector Similarity & Conflict Judge      │
   └──────────────────────┬────────────────────────┘
                          │
                          ▼
   ┌───────────────────────────────────────────────┐
   │         Stage D: Human Airlock Gate           │
   │         Mandatory Review & Approval           │
   └──────────────────────┬────────────────────────┘
                          │
             ┌────────────┴────────────┐
             ▼                         ▼
   ┌───────────────────┐     ┌───────────────────┐
   │  Tracker Adapter  │     │ Notifier Adapter  │
   │  (Mock / GitHub)  │     │ (Console / Slack) │
   └───────────────────┘     └───────────────────┘
```

* **Frontend:** Responsive Glassmorphic Single-Page Application (HTML5, Tailwind, Modern JS) with Dark & Light theme support.
* **Backend:** Python FastAPI with async lifespan management and CORS middleware.
* **Database:** SQLite with SQLAlchemy ORM (PostgreSQL-ready).
* **Scheduling:** APScheduler background engine for reminders and digest routines.

---

## 🏃 Running Locally

### 1. Clone the repository
```bash
git clone https://github.com/kavitha104/actionloop.git
cd actionloop
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Start the server
```bash
python cadence_app/run_server.py
```

Open your browser at **`http://localhost:8080`** to view the app!

---

## 👥 Contributors

* **Kavitha** ([@kavitha104](https://github.com/kavitha104))
