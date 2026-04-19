# 🎫 Ticket Resolution System

RAG-based ticket resolution chatbot extended with **auto-closure** and **automated resolution notifications**.

---

## Table of Contents

1. [Project Structure](#project-structure)
2. [Feature Overview](#feature-overview)
3. [Setup & Configuration](#setup--configuration)
4. [Running the App](#running-the-app)
5. [API Reference](#api-reference)
6. [Webhook Integration](#webhook-integration)
7. [Architecture Diagram](#architecture-diagram)

---

## Project Structure

```
ticket-resolution-system/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py
│   │   │   └── routes/
│   │   │       ├── chat.py               # Existing: RAG chatbot
│   │   │       ├── config.py             # Existing: config CRUD
│   │   │       ├── health.py             # Existing: health check
│   │   │       ├── rag_admin.py          # Existing: ingest data sources
│   │   │       ├── theme.py              # Existing: UI theming
│   │   │       ├── ticket_lifecycle.py   # ✨ NEW: auto-closure endpoints
│   │   │       ├── notification.py       # ✨ NEW: notification endpoints
│   │   │       └── webhooks.py           # ✨ NEW: Jira / SharePoint receivers
│   │   ├── contracts/                    # Existing: provider abstractions
│   │   ├── core/
│   │   │   ├── exceptions.py
│   │   │   └── settings.py
│   │   ├── factories/
│   │   │   └── provider_factory.py
│   │   ├── providers/
│   │   │   ├── embeddings/
│   │   │   ├── llm/
│   │   │   └── vectorstores/
│   │   ├── repositories/
│   │   │   ├── ai_config_repository.py
│   │   │   ├── rag_admin_repository.py
│   │   │   └── ticket_lifecycle_repository.py  # ✨ NEW: events + notif log
│   │   ├── schemas/
│   │   │   ├── chat.py
│   │   │   ├── rag_admin.py
│   │   │   ├── ticket_lifecycle.py       # ✨ NEW: auto-close request/result
│   │   │   └── notification.py           # ✨ NEW: notify request/result
│   │   ├── services/
│   │   │   ├── ingestion_service.py
│   │   │   ├── rag_service.py
│   │   │   ├── ingestors/
│   │   │   │   ├── jira_ingestor.py
│   │   │   │   ├── sharepoint_ingestor.py
│   │   │   │   └── sharepoint_local_ingestor.py
│   │   │   ├── ticket_lifecycle/         # ✨ NEW
│   │   │   │   └── auto_closure_service.py
│   │   │   └── notification/             # ✨ NEW
│   │   │       ├── dispatcher.py         # SMTP + mock/log
│   │   │       └── notification_service.py
│   │   └── main.py
│   ├── config_store/
│   │   └── client-a_rag_config.json
│   ├── database/
│   │   ├── db_seed.py
│   │   ├── migrate.py                    # ✨ NEW: adds ticket_events + notification_log
│   │   └── ticket.db
│   ├── faiss_store/
│   ├── .env
│   ├── .env.example
│   ├── Dockerfile
│   └── requirements.txt
└── frontend/
    └── src/
        ├── api/
        ├── components/
        ├── pages/
        └── styles/
```

---

## Feature Overview

### 1. Existing — RAG Chatbot
Users ask questions about past tickets via the chat UI. The RAG pipeline searches the FAISS vector store (built from Jira + SharePoint data) and returns matching resolutions with confidence scores.

### 2. ✨ Auto-Closure

**How it works:**

```
New ticket arrives → POST /api/v1/tickets/auto-close
                          │
                          ▼
                   RAGService.ask()          ← FAISS vector search
                          │
                   best match confidence
                          │
              ┌───────────┴───────────┐
         ≥ threshold              < threshold
              │                       │
        auto_closed=True         auto_closed=False
        (caller updates Jira/SP)  (routed for human review)
              │
        record in ticket_events
```

- **Threshold**: configurable per request (`confidence_threshold` field, default `0.85`).  
- **Idempotent**: duplicate ticket IDs are detected and skipped.  
- **No direct Jira API calls**: the service returns `auto_closed`, `resolution`, and `matched_ticket_id`. The caller (webhook / scheduler) owns the Jira REST call — keeping this layer testable.

### 3. ✨ Resolution Notification

**How it works:**

```
New ticket arrives → POST /api/v1/notifications/send
                          │
                          ▼
                   RAGService.ask()          ← top-k matches
                          │
                   build HTML table
                          │
              ┌───────────┴───────────┐
         SMTP configured         no SMTP
              │                       │
        send real email          log to console
              │
        record in notification_log
```

**Table columns**: Ticket ID · Description · Resolution · Root Cause · Type · Status · Priority · Confidence %

**Email modes**:
- **SMTP mode** — set `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` in `.env`.
- **Mock mode** (default) — HTML table is logged to the server console. Ideal for development and demos.

### 4. ✨ Webhook Integration (Jira + SharePoint)

Both features trigger automatically when a ticket is created:

```
Jira "issue_created" webhook → POST /api/v1/webhooks/jira?tenant_id=client-a
SharePoint Power Automate    → POST /api/v1/webhooks/sharepoint?tenant_id=client-a
```

Each webhook handler runs **notification + auto-closure in one call** and returns a combined JSON result.

---

## Setup & Configuration

### 1. Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env:
#   - Set GOOGLE_API_KEY or OPENAI_API_KEY
#   - Optionally set SMTP_* for real email delivery
#   - Adjust AUTO_CLOSE_CONFIDENCE_THRESHOLD (default 0.85)
```

### 3. Seed + migrate database
```bash
# From backend/
python database/db_seed.py    # creates users, sessions, chats tables
python database/migrate.py    # creates ticket_events, notification_log tables
```
> **Note**: The migration also runs automatically on every app startup via the `@app.on_event("startup")` hook — it is fully idempotent.

---

## Running the App

```bash
# Backend
cd backend
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Swagger UI: http://localhost:8000/docs

---

## API Reference

### Auto-Closure

#### `POST /api/v1/tickets/auto-close`
Evaluate whether a new ticket should be auto-closed.

**Request body**
```json
{
  "tenant_id": "client-a",
  "ticket_id": "PROJ-999",
  "source_type": "jira",
  "description": "User cannot login after password reset",
  "assignee_email": "dev@company.com",
  "confidence_threshold": 0.85
}
```

**Response**
```json
{
  "ticket_id": "PROJ-999",
  "auto_closed": true,
  "confidence_score": 0.9123,
  "matched_ticket_id": "PROJ-412",
  "resolution": "Clear browser cache and reset session cookie.",
  "root_cause": "Stale session token not invalidated on password change.",
  "reason": "Confidence 0.9123 ≥ threshold 0.85 → auto-closed."
}
```

#### `GET /api/v1/tickets/events/{tenant_id}?limit=50`
Audit log of auto-closure decisions.

---

### Notifications

#### `POST /api/v1/notifications/send`
Trigger a resolution notification for a new ticket.

**Request body**
```json
{
  "tenant_id": "client-a",
  "ticket_id": "PROJ-999",
  "source_type": "jira",
  "description": "User cannot login after password reset",
  "assignee_email": "dev@company.com",
  "top_k": 5
}
```

**Response**
```json
{
  "ticket_id": "PROJ-999",
  "assignee_email": "dev@company.com",
  "channel": "email",
  "status": "sent",
  "resolutions": [ ... ],
  "message": "Resolution sent to dev@company.com."
}
```

Possible `channel` values: `email`, `mock`  
Possible `status` values: `sent`, `mock_sent`, `failed`

#### `GET /api/v1/notifications/log/{tenant_id}?limit=50`
Notification history for a tenant.

---

### Webhooks

#### `POST /api/v1/webhooks/jira?tenant_id=client-a`
Accepts Jira `jira:issue_created` event payload.

#### `POST /api/v1/webhooks/sharepoint?tenant_id=client-a`
Accepts a JSON body:
```json
{
  "ticket_id": "SP-001",
  "description": "Cannot access shared drive after VPN update",
  "assignee_email": "support@company.com"
}
```

Both return:
```json
{
  "ticket_id": "...",
  "tenant_id": "...",
  "notification": { "status": "mock_sent", "channel": "mock", "message": "..." },
  "auto_closure": { "auto_closed": false, "confidence_score": 0.71, "reason": "..." }
}
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI Backend                          │
│                                                                 │
│  ┌──────────────┐  ┌─────────────────┐  ┌──────────────────┐   │
│  │  /chat        │  │ /tickets/       │  │ /notifications/  │   │
│  │  (chatbot)    │  │ auto-close      │  │ send             │   │
│  └──────┬────────┘  └────────┬────────┘  └────────┬─────────┘   │
│         │                   │                     │             │
│         └──────────┬─────────┘                    │             │
│                    ▼                              ▼             │
│             ┌─────────────┐              ┌────────────────┐     │
│             │  RAGService  │              │ Notification   │     │
│             │  (FAISS +    │◄─────────────│ Service        │     │
│             │   LLM)       │              └───────┬────────┘     │
│             └─────────────┘                      │              │
│                    │                    ┌─────────▼──────────┐   │
│         ┌──────────▼──────────┐         │  Dispatcher         │   │
│         │ AutoClosureService  │         │  SMTP / Mock-log   │   │
│         └──────────┬──────────┘         └────────────────────┘   │
│                    │                                             │
│         ┌──────────▼──────────────────────────────┐             │
│         │         SQLite  (ticket.db)              │             │
│         │  ticket_events  │  notification_log      │             │
│         └─────────────────────────────────────────┘             │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  /webhooks/jira   /webhooks/sharepoint                   │   │
│  │  (auto-runs notification + auto-closure on ticket create)│   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         ▲                              ▲
         │                              │
   Jira Webhook                  SharePoint
   (issue_created)               Power Automate
```

---

## Database Tables Added

### `ticket_events`
| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | |
| tenant_id | TEXT | |
| ticket_id | TEXT | Incoming ticket |
| source_type | TEXT | `jira` or `sharepoint_local` |
| event_type | TEXT | `auto_closed`, `skipped`, `notified` |
| confidence | REAL | RAG best-match score |
| matched_ticket_id | TEXT | Best match from knowledge base |
| resolution | TEXT | Suggested resolution text |
| reason | TEXT | Human-readable decision rationale |
| created_at | TEXT | ISO 8601 UTC |

### `notification_log`
| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | |
| tenant_id | TEXT | |
| ticket_id | TEXT | |
| assignee_email | TEXT | |
| channel | TEXT | `email` or `mock` |
| status | TEXT | `sent`, `mock_sent`, `failed` |
| payload | TEXT | JSON of what was sent |
| error_message | TEXT | Populated on failure |
| created_at | TEXT | ISO 8601 UTC |
