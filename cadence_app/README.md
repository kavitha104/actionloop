# Cadence: Meeting-to-Execution Agent Server

> **Enterprise-grade meeting execution system that bridges conversational decisions into verified tracker deliverables, tracks persistent cross-meeting memory, detects conflicting agreements, and enforces a strict human-in-the-loop confirmation gate.**

---

## 🌟 Core Architecture & Capabilities

1. **Transcript Ingestion with Speaker Attribution (`POST /api/ingest`)**
   - Ingests meeting dialogue formatted as `Speaker: dialogue` or `[Speaker] dialogue`.
   - Extracts structured intent, separating **Team Decisions** (`dec`) from **Action Items** (`act`).
   - Automatically attributes owners and parses target deadlines (`by Friday`, `by March 14`, etc.).
   - Attaches verbatim quotes and AI extraction confidence scores.

2. **Cross-Meeting Memory (`GET /api/memory`)**
   - Persistent SQLite (WAL mode) datastore preserving decisions across past meetings.
   - Retains context, meeting origin, date, topic domain, and direct quotes.
   - Automatically handles superseding state when older architectural decisions are legitimately replaced.

3. **Conflict & Contradiction Detection (`GET /api/conflicts`)**
   - Evaluates new meeting items against active memory.
   - Catches **Hard Contradictions** (e.g., launching on March 14 when previously locked to April 2; migrating to MongoDB when PostgreSQL was agreed upon).
   - Flags **Duplicates** (re-confirming unchanged decisions).
   - Flags **Soft/Overlap Conflicts** (inter-dependent architectural modifications).

4. **Human-in-the-Loop Confirmation Gate (`POST /api/confirm-and-post`)**
   - **Nothing is posted to external systems automatically.**
   - Review modal allows editing owners, altering deadlines, deselecting items, and picking which conflicting decision wins (`keep_new`, `keep_existing`, or `both`).
   - Only approved items are promoted to active memory and downstream trackers.

5. **Tracker Integration Sync (`GET /api/tasks`, `PATCH /api/tasks/{id}/status`)**
   - Generates tickets with project key formatting for **Linear** (`LIN-xxx`), **Jira** (`JRA-xxx`), **Asana** (`ASA-xxx`), and internal tracker.
   - Maintains two-way status tracking (`open`, `in_progress`, `done`).

6. **Automated Reminders Before Deadlines (`GET /api/reminders`, `POST /api/reminders/{id}/send`)**
   - Queues proactive reminders triggered 1–2 days before target deliverables.
   - Dispatches actionable notifications to assignees.

7. **Weekly Digest per Person & Team Workload (`GET /api/digest/person/{name}`, `GET /api/digest/team`)**
   - Generates personalized digests per team member detailing:
     - Open deliverables
     - Upcoming deadlines
     - Active decisions owned
     - Workload capacity scoring and distribution

---

## 🚀 Quickstart & Server Launch

### Prerequisites
- Python 3.10+
- Installed packages: `fastapi`, `uvicorn`, `pydantic`

### Run the Server
```powershell
python run_server.py
```
Or directly via uvicorn:
```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- **Interactive Web App & Workspace**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Swagger / OpenAPI Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc Technical Specification**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 📡 API Reference Overview

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/ingest` | Ingests transcript, extracts decisions/tasks, and runs conflict detection against memory. |
| `POST` | `/api/confirm-and-post` | Human approval gate; commits tasks to tracker and updates persistent memory. |
| `GET` | `/api/memory` | Queries cross-meeting decisions memory (supports topic and superseded filtering). |
| `GET` | `/api/conflicts` | Lists detected conflicts between new proposals and past decisions. |
| `GET` | `/api/tasks` | Lists all created tracker tickets and current statuses. |
| `PATCH` | `/api/tasks/{id}/status` | Updates ticket progress (`open`, `in_progress`, `done`). |
| `GET` | `/api/reminders` | Retrieves scheduled deadline reminders. |
| `POST` | `/api/reminders/{id}/send`| Dispatches a deadline reminder notification. |
| `GET` | `/api/digest/person/{name}`| Generates personal weekly digest and workload metrics. |
| `GET` | `/api/digest/team` | Team-wide weekly workload matrix and open conflicts. |
| `GET` | `/api/audit-logs` | Comprehensive system audit log. |
