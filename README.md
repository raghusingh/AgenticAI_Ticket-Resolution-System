# 🎫 Ticket Resolution System

An intelligent, multi-agent ticket resolution platform powered by RAG (Retrieval Augmented Generation), LangGraph, and LangChain. The system automatically ingests tickets from Jira and SharePoint, finds similar resolved tickets using vector search, notifies assignees via email, and autonomously closes or escalates tickets based on AI confidence scores.

---

## 📋 Table of Contents

- [Architecture Overview](#architecture-overview)
- [Multi-Agent System](#multi-agent-system)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Features](#features)
- [API Endpoints](#api-endpoints)
- [Setup & Installation](#setup--installation)
- [Configuration](#configuration)
- [How It Works](#how-it-works)
- [Vector Database](#vector-database)
- [Database Schema](#database-schema)
- [Testing](#testing)
- [Roadmap](#roadmap)

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                             │
│         Jira REST API v3 (tickets + comments)                   │
│         SharePoint Local (CSV / Excel files)                    │
└──────────────────────┬──────────────────────────────────────────┘
                       │ ingest · embed · deduplicate
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│               QDRANT VECTOR DATABASE  (primary)                 │
│         Collection: client-a_KB_All                             │
│         Cosine similarity · Real-time upserts · No rebuild      │
│         Switchable to FAISS via config                          │
└──────────────┬────────────────────────────────────────----------┘
               │
       ┌───────┴────────┐
       ▼                ▼
┌────────────────┐  ┌────────────────────────────────────────────┐
│   React UI     │  │              APScheduler                   │
│ /api/v1/chat   │  │  polls Jira every 10 min                   │
│ RAGService     │  │  max_instances=1 · coalesce=True           │
│ Split reranker │  │  completely silent when no new tickets      │
└────────────────┘  └──────────────┬─────────────────────────────┘
                                   │ new ticket detected
                                   ▼
                    ┌──────────────────────────────┐
                    │   COORDINATOR AGENT (LLM #1) │
                    │   plans execution order       │
                    └──────┬───────────────────────┘
                           │
           ┌───────────────┼──────────────────┐
           ▼               ▼                  ▼
  ┌──────────────┐ ┌──────────────┐  ┌──────────────────┐
  │  INGESTION   │ │  RESOLUTION  │  │  NOTIFICATION    │
  │  AGENT #2    │ │  AGENT #3    │  │  AGENT #4        │
  │              │ │              │  │                  │
  │ reason+act   │ │ reason+act   │  │ reason+act       │
  │ merged node  │ │ merged node  │  │ merged node      │
  └──────────────┘ └──────────────┘  └──────────────────┘
                                              │
                                    ┌─────────▼──────────┐
                                    │  CLOSURE AGENT #5  │
                                    │  reason+act merged │
                                    │  ≥0.85 → close     │
                                    │  0.6-0.85 → escal. │
                                    └────────────────────┘
```

---

## 🤖 Multi-Agent System

5 specialized LangGraph agents, each with its own LLM reasoning loop.

### Critical Architecture Fix — Merged Nodes
All agents previously used separate `reason_node` → `act_node`. LangGraph was **silently dropping internal state keys** (e.g. `_ingest_decision`) between nodes because they weren't declared in `TicketState`. This caused:
- Ingestion agent deciding "ingest" but always skipping
- Notification agent always notifying regardless of LLM decision
- Closure agent ignoring LLM decision

**Fix:** All agents now use a single `reason_and_act_node` — decide and act in one function, no state passing needed.

### 1. Coordinator Agent
- Plans execution: Ingestion → Resolution → Notification → Closure
- Handles agent failures gracefully — others still run
- None-safe formatting for all confidence values

### 2. Ingestion Agent
- Checks Qdrant KB freshness (1-hour threshold)
- Re-ingests from Jira (with comments) + SharePoint when stale
- Merged node — no state-passing bug

### 3. Resolution Agent
- Searches Qdrant for similar tickets
- LLM ranks candidates; full JSON sanitization for null values
- Only passes **closed tickets with resolution** to Notification Agent

### 4. Notification Agent
- Decides priority (high/normal) based on confidence
- Sends HTML email to assignee + CC recipients
- Skips sending if no resolved tickets (prevents blank emails)

### 5. Closure Agent
- confidence ≥ 0.85 → close in Jira (transition to Done + comment)
- confidence 0.60–0.85 → escalate for human review
- confidence < 0.60 → skip
- All confidence values None-safe

### Agent vs UI Search

| Action | Path | Agents |
|---|---|---|
| Chat UI search | `POST /api/v1/chat` → RAGService | ❌ None |
| New ticket (scheduler) | APScheduler → Coordinator | ✅ All 5 |
| Manual trigger | `POST /api/v1/agent/process-ticket` | ✅ All 5 |
| Close ticket on UI | `POST /api/v1/tickets/close` | ❌ None |

---

## 🛠️ Tech Stack

### Backend
| Component | Technology |
|---|---|
| API Framework | FastAPI + Python 3.11 |
| Agent Orchestration | LangGraph |
| LLM | OpenAI GPT-4o-mini / Google Gemini |
| Embeddings | OpenAI text-embedding-3-small |
| Vector Database | **Qdrant** (primary) / FAISS (fallback) |
| Database | SQLite |
| Scheduler | APScheduler |
| Email | SMTP (Gmail) |

### Frontend
| Component | Technology |
|---|---|
| Framework | React + Vite |
| HTTP Client | Axios |

### Integrations
| Source | Method |
|---|---|
| Jira | REST API v3 + comment fetching per ticket |
| SharePoint Local | File system reader |
| Email | Gmail SMTP with App Password + CC |

---

## 📁 Project Structure

```
ticket-resolution-system/
├── backend/
│   ├── app/
│   │   ├── api/routes/
│   │   │   ├── agent_router.py              # POST /api/v1/agent/process-ticket
│   │   │   ├── chat.py                      # POST /api/v1/chat
│   │   │   ├── close_ticket.py              # POST /api/v1/tickets/close
│   │   │   └── rag_admin.py                 # Ingestion endpoints
│   │   ├── core/
│   │   │   └── db_path.py                   # ✅ Single DB path source of truth
│   │   ├── repositories/
│   │   │   └── ticket_lifecycle_repository.py  # get_closed_tickets() for dropdown
│   │   ├── schemas/
│   │   │   └── chat.py                      # ✅ confidence_score: Optional[float]
│   │   └── services/
│   │       ├── agent/agents/
│   │       │   ├── agent_state.py           # ✅ All internal fields in TypedDict
│   │       │   ├── coordinator_agent.py     # ✅ None-safe formatting
│   │       │   ├── ingestion_agent.py       # ✅ Merged reason+act node
│   │       │   ├── resolution_agent.py      # ✅ Merged + JSON sanitization
│   │       │   ├── notification_agent.py    # ✅ Merged reason+act node
│   │       │   └── closure_agent.py         # ✅ Merged reason+act node
│   │       ├── scheduler/
│   │       │   └── ticket_scheduler.py      # ✅ max_instances=1, silent idle
│   │       ├── ingestion_service.py         # ✅ QdrantVectorDB + FAISSVectorDB
│   │       └── rag_service.py               # ✅ Split reranking open vs closed
│   ├── config_store/
│   │   └── client-a_rag_config.json         # ✅ vector_store section added
│   ├── database/
│   │   ├── migrate.py                       # Creates all DB tables
│   │   ├── clear_scheduler.py               # Clear processed ticket cache
│   │   └── ticket.db                        # SQLite (auto-created)
│   ├── .env
│   └── requirements.txt                     # ✅ qdrant-client added
└── frontend/src/
    ├── api/
    │   └── chatApi.js                       # ✅ triggerIngestion added
    └── pages/
        └── ChatPage.jsx                     # ✅ Close dialog, auto-refresh
```

---

## ✨ Features

### RAG Pipeline
- **Two-stage retrieval** — Qdrant vector search → LLM reranking
- **Split reranking** — open and closed tickets handled separately:
  - Closed tickets: strict filter (same problem type, has resolution)
  - Open tickets: lenient filter (topic match by description only)
- **Score threshold** — configurable `score_threshold` in models config (default 1.5)
- **Comment ingestion** — Jira comments fetched and stored per ticket

### Vector Database — Qdrant
- Real-time upserts — no full index rebuild when a ticket closes
- Automatic deduplication by point ID (MD5 hash of ticket_id)
- Cosine similarity (better for text than L2/FAISS)
- Web dashboard at `http://localhost:6333/dashboard`
- Switchable back to FAISS via config with no code changes

### Multi-Agent Automation
- **5 agents** each with own LLM reasoning loop
- **Merged nodes** — avoid LangGraph state-passing bug
- **Auto-closure** at 85% confidence threshold
- **Graceful failures** — one agent fails, others continue
- **None-safe** — all confidence/format values sanitized

### Scheduler
- **Silent when idle** — zero console noise when no new tickets
- **No overlap** — `max_instances=1` prevents parallel job runs
- **Coalesce** — missed runs skipped, not piled up
- **10-minute interval** — enough time for 5 LLM calls

### Email Notifications
- HTML resolution table with Source, Ticket ID, Description, Resolution, Confidence
- CC recipients via `SMTP_CC` in `.env`
- Skipped if no resolved tickets (no blank emails)
- Uses `prefetched_tickets` — no duplicate RAG call

### UI Features
- Search returns open + closed tickets (split reranked)
- Open tickets shown with blank resolution + `-` confidence
- Close button only on open rows
- Close dialog: selected ticket shown as label (read-only), resolution dropdown auto-fills
- After close: re-ingest → 1.5s wait → re-search → table refreshes automatically

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/chat` | RAG search — direct Qdrant, no agent |
| `POST` | `/api/v1/agent/process-ticket` | Trigger all 5 agents manually |
| `GET` | `/api/v1/agent/status` | LangGraph availability |
| `POST` | `/api/v1/tickets/close` | Close ticket in Jira + DB |
| `GET` | `/api/v1/tickets/closed/{tenant_id}` | Closed tickets for dropdown |
| `POST` | `/api/v1/admin/rag-config/ingest/{tenant_id}` | Run ingestion |
| `GET` | `/api/v1/admin/rag-config/{tenant_id}` | Get tenant config |
| `POST` | `/api/v1/login` | Session auth |
| `GET` | `/api/v1/health` | Health check |

Swagger UI: `http://localhost:8000/docs`

---

## 🚀 Setup & Installation

### Prerequisites
- Python 3.11
- Node.js 18+
- Docker (for Qdrant)

### 1. Start Qdrant
```bash
docker run -d -p 6333:6333 -p 6334:6334 \
  -v qdrant_data:/qdrant/storage \
  qdrant/qdrant
```
Verify: `http://localhost:6333/dashboard`

### 2. Setup backend
```bash
cd backend
py -3.11 -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux
pip install -r requirements.txt
```

### 3. Configure `.env`
```env
AUTO_CLOSE_CONFIDENCE_THRESHOLD=0.85

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your_16_char_app_password
SMTP_CC=

SCHEDULER_ENABLED=true
SCHEDULER_JIRA_INTERVAL_MINUTES=10
SCHEDULER_SHAREPOINT_INTERVAL_MINUTES=10
```

### 4. Configure tenant (`config_store/client-a_rag_config.json`)
```json
{
  "tenant_id": "client-a",
  "models": {
    "llm_provider": "OpenAI",
    "llm_model_name": "gpt-4o-mini",
    "embedding_provider": "OpenAI",
    "embedding_model_name": "text-embedding-3-small",
    "score_threshold": 1.5
  },
  "vector_store": {
    "provider": "qdrant",
    "host": "localhost",
    "port": 6333,
    "api_key": ""
  },
  "data_sources": [
    {
      "source_type": "jira",
      "source_url": "https://your-domain.atlassian.net/",
      "username": "your@email.com",
      "token": "your_jira_api_token",
      "project_key": "SCRUM",
      "is_enabled": true
    }
  ],
  "secrets": {
    "llm_api_key": "sk-...",
    "embedding_api_key": "sk-..."
  }
}
```

### 5. Run migrations and start server
```bash
python database/migrate.py
python -m uvicorn app.main:app --reload
```

### 6. Run ingestion
```
POST http://localhost:8000/api/v1/admin/rag-config/ingest/client-a
```

### 7. Start frontend
```bash
cd frontend
npm install
npm run dev
```

---

## 🔄 How It Works

### UI Search (No Agent)
```
User types query → POST /api/v1/chat
      ↓
RAGService.ask()
      ↓
ingestion_service.query() → Qdrant search → score threshold filter
      ↓
_build_ticket_rows() → open = blank resolution/confidence
      ↓
_rerank_tickets() splits into:
  ├── _rerank_closed()              → strict LLM filter
  └── _filter_open_by_description() → lenient LLM filter
      ↓
Results table — relevant open + closed tickets
```

### New Ticket Auto-Processing
```
APScheduler polls every 10 min
  → silent if no new tickets
      ↓
New ticket detected
      ↓
Coordinator Agent → plans execution
      ↓
Ingestion Agent   → check KB age → re-ingest if stale
      ↓
Resolution Agent  → Qdrant search → LLM ranks → best match
      ↓
Notification Agent → email if resolved tickets exist
      ↓
Closure Agent     → close / escalate / skip by confidence
      ↓
Ticket marked processed in scheduler_processed
```

---

## 🗄️ Vector Database

### Switching between Qdrant and FAISS
Change `provider` in `client-a_rag_config.json` and re-run ingestion:

```json
"vector_store": { "provider": "qdrant" }   // Qdrant (recommended)
"vector_store": { "provider": "faiss" }    // FAISS fallback
```

| Feature | FAISS | Qdrant |
|---|---|---|
| Scale | Millions | Billions |
| Upsert | Full rebuild | Real-time |
| Deduplication | Manual | Automatic |
| Distance | L2 | Cosine |
| Deployment | File-based | Docker |

---

## 🗄️ Database Schema

Path: `backend/database/ticket.db` — enforced by `app/core/db_path.py`

| Table | Purpose | Key columns |
|---|---|---|
| `ticket_events` | All lifecycle events | ticket_id, event_type, confidence, resolution |
| `notification_log` | Outgoing emails | ticket_id, assignee_email, channel, status |
| `scheduler_processed` | Prevents duplicate runs | tenant_id, ticket_id, content_hash |
| `users` | Auth | username, password_hash |
| `sessions` | Sessions | session_id, username, expires_at |

Event types: `auto_closed` · `escalated` · `notified` · `skipped`

---

## 🧪 Testing

### Test multi-agent system
```bash
cd backend
python -c "
import sys; sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()
from app.services.agent.agents.coordinator_agent import run_multi_agent_system
result = run_multi_agent_system(
    tenant_id='client-a',
    ticket_id='SCRUM-TEST',
    source_type='jira',
    description='500 Internal Server Error on website',
    assignee_email='your@email.com',
)
print(result)
"
```

### Verify Qdrant collection
```bash
python -c "
from qdrant_client import QdrantClient
c = QdrantClient(host='localhost', port=6333, https=False)
for col in c.get_collections().collections:
    print(col.name, '->', c.count(col.name).count, 'vectors')
"
```

### Clear scheduler cache
```bash
python database/clear_scheduler.py --all
python database/clear_scheduler.py --ticket SCRUM-30
```

### Check DB events
```bash
python -c "
import sqlite3
from app.core.db_path import get_db_path
conn = sqlite3.connect(get_db_path())
for r in conn.execute('SELECT ticket_id, event_type, confidence, created_at FROM ticket_events ORDER BY created_at DESC LIMIT 10'):
    print(r)
"
```

---

## 🗺️ Roadmap

| Phase | Status | Description |
|---|---|---|
| Phase 1 — POC | ✅ Complete | RAG + 5-agent LangGraph + Qdrant + React UI |
| Phase 2 — Harden | 🔜 Next | PostgreSQL, Redis cache, multi-tenant isolation |
| Phase 3 — Scale | ⬜ Planned | Celery queue, Jira webhooks, LangSmith tracing |
| Phase 4 — Production | ⬜ Planned | Kubernetes, Grafana, MCP server, enterprise SSO |