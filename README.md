# 🎫 Ticket Resolution System

An intelligent, multi-agent ticket resolution platform powered by RAG (Retrieval Augmented Generation), LangGraph, and LangChain. The system automatically ingests tickets from Jira and SharePoint, finds similar resolved tickets using vector search, notifies assignees via email, and autonomously closes or escalates tickets based on confidence scores.

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
- [UI Guide](#ui-guide)

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                             │
│           Jira                      SharePoint Local            │
└──────────────────────┬──────────────────────────────────────────┘
                       │ poll / ingest
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                   INGESTION PIPELINE                            │
│  JiraIngestor → fetch tickets + comments → chunk → embed       │
│  SharePointLocalIngestor → read local files → chunk → embed    │
│  FAISSVectorDB → deduplicate by ticket_id → upsert vectors     │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                  FAISS VECTOR DATABASE                          │
│         backend/faiss_store/client-a_KB_All.index              │
└──────────────┬────────────────────────────────────────────────-─┘
               │
      ┌────────┴─────────┐
      ▼                  ▼
┌───────────┐     ┌──────────────────────────────────────────────┐
│ React UI  │     │              APScheduler                     │
│ (search)  │     │  polls Jira every N minutes                  │
│           │     │  detects new tickets automatically           │
└─────┬─────┘     └────────────────────┬─────────────────────────┘
      │                                │ new ticket detected
      │ POST /api/v1/chat              ▼
      │ (direct RAG, no agent)  ┌──────────────────────────────┐
      │                         │   COORDINATOR AGENT (LLM)    │
      ▼                         │   plans execution order       │
┌───────────┐                   └──────┬───────────────────────-┘
│ RAGService│                          │
│ (fast     │         ┌────────────────┼──────────────────────┐
│ semantic  │         ▼                ▼                      ▼
│ search)   │  ┌─────────────┐ ┌─────────────┐ ┌────────────────┐
└───────────┘  │ INGESTION   │ │ RESOLUTION  │ │ NOTIFICATION   │
               │ AGENT (LLM) │ │ AGENT (LLM) │ │ AGENT (LLM)    │
               │             │ │             │ │                │
               │ Decides if  │ │ Searches    │ │ Decides who    │
               │ KB needs    │ │ FAISS, ranks│ │ to notify and  │
               │ refresh     │ │ best match  │ │ sends email    │
               └─────────────┘ └─────────────┘ └────────────────┘
                                                        │
                                               ┌────────▼───────┐
                                               │ CLOSURE AGENT  │
                                               │ (LLM)          │
                                               │                │
                                               │ conf >= 0.85   │
                                               │ → close ticket │
                                               │ conf < 0.85    │
                                               │ → escalate     │
                                               └────────────────┘
```

---

## 🤖 Multi-Agent System

The system uses **5 specialized LangGraph agents**, each with its own LLM reasoning loop:

### 1. Coordinator Agent
- **Role:** Orchestrates all other agents
- **Decides:** Execution plan and order
- **Runs:** First and last — plans then summarizes
- **File:** `app/services/agent/agents/coordinator_agent.py`

### 2. Ingestion Agent
- **Role:** Keeps the knowledge base fresh
- **Decides:** Whether to re-ingest based on KB age
- **Rule:** Re-ingest if KB is older than 1 hour or doesn't exist
- **File:** `app/services/agent/agents/ingestion_agent.py`

### 3. Resolution Agent
- **Role:** Finds the best matching resolved ticket
- **Decides:** Which candidate is the best match and why
- **Returns:** Best ticket ID, resolution text, confidence score
- **File:** `app/services/agent/agents/resolution_agent.py`

### 4. Notification Agent
- **Role:** Sends resolution suggestions to the assignee
- **Decides:** Whether to notify and at what priority
- **Sends:** HTML email with resolution table (via SMTP)
- **File:** `app/services/agent/agents/notification_agent.py`

### 5. Closure Agent
- **Role:** Closes or escalates the ticket
- **Decides:** Based on confidence threshold (0.85)
- **Actions:** Close in Jira → Done, or escalate for human review
- **File:** `app/services/agent/agents/closure_agent.py`

### Agent vs UI Search

| Action | Path | Agents Used |
|---|---|---|
| Search on chat UI | `POST /api/v1/chat` → RAGService | ❌ None (direct FAISS) |
| New ticket (scheduler) | APScheduler → Coordinator | ✅ All 5 agents |
| Manual agent trigger | `POST /api/v1/agent/process-ticket` | ✅ All 5 agents |
| Close ticket on UI | `POST /api/v1/tickets/close` | ❌ None (direct service) |

---

## 🛠️ Tech Stack

### Backend
| Component | Technology |
|---|---|
| API Framework | FastAPI |
| Agent Orchestration | LangGraph |
| Agent Tools | LangChain |
| LLM | OpenAI GPT-4o-mini / Google Gemini |
| Embeddings | OpenAI text-embedding-3-small / Google |
| Vector Database | FAISS (custom FAISSVectorDB) |
| Relational Database | SQLite |
| Scheduler | APScheduler |
| Email | SMTP (Gmail) |
| Auth | Session-based (SQLite) |

### Frontend
| Component | Technology |
|---|---|
| Framework | React (Vite) |
| HTTP Client | Axios |
| Styling | CSS + inline styles |

### Integrations
| Source | Method |
|---|---|
| Jira | REST API v3 (`/rest/api/3/search/jql`) |
| SharePoint Local | File system reader |
| Email | Gmail SMTP with App Password |

---

## 📁 Project Structure

```
ticket-resolution-system/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py                          # Login/session auth
│   │   │   └── routes/
│   │   │       ├── agent_router.py              # POST /api/v1/agent/process-ticket
│   │   │       ├── chat.py                      # POST /api/v1/chat (RAG search)
│   │   │       ├── close_ticket.py              # POST /api/v1/tickets/close
│   │   │       ├── config.py                    # Tenant config management
│   │   │       ├── health.py                    # GET /api/v1/health
│   │   │       ├── notification.py              # Notification endpoints
│   │   │       ├── rag_admin.py                 # Ingestion + config endpoints
│   │   │       ├── scheduler.py                 # Scheduler control
│   │   │       ├── ticket_lifecycle.py          # Lifecycle events
│   │   │       ├── theme.py                     # UI theme settings
│   │   │       └── webhooks.py                  # Webhook receiver
│   │   ├── core/
│   │   │   ├── db_path.py                       # Single source of truth for DB path
│   │   │   └── settings.py                      # App settings
│   │   ├── factories/
│   │   │   └── provider_factory.py              # LLM/Embedding/VectorStore factory
│   │   ├── providers/
│   │   │   ├── embeddings/                      # OpenAI + Gemini embedding providers
│   │   │   ├── llm/                             # OpenAI + Gemini LLM providers
│   │   │   └── vectorstores/                    # FAISS + Chroma providers
│   │   ├── repositories/
│   │   │   ├── ai_config_repository.py          # Tenant AI config reader
│   │   │   ├── rag_admin_repository.py          # RAG admin operations
│   │   │   └── ticket_lifecycle_repository.py   # Events + notifications DB
│   │   ├── schemas/
│   │   │   ├── chat.py                          # Chat request/response schemas
│   │   │   ├── notification.py                  # NotifyRequest, ResolutionRow
│   │   │   ├── rag_admin.py                     # RAG admin schemas
│   │   │   └── ticket_lifecycle.py              # AutoCloseRequest/Result
│   │   └── services/
│   │       ├── agent/
│   │       │   ├── agent_tools.py               # Legacy single-agent tools
│   │       │   ├── ticket_agent.py              # Legacy single-agent (fallback)
│   │       │   └── agents/                      # ✅ Multi-agent system
│   │       │       ├── agent_state.py           # Shared state TypedDict
│   │       │       ├── coordinator_agent.py     # Orchestrator agent
│   │       │       ├── ingestion_agent.py       # KB freshness agent
│   │       │       ├── resolution_agent.py      # RAG search + ranking agent
│   │       │       ├── notification_agent.py    # Email notification agent
│   │       │       └── closure_agent.py         # Close/escalate agent
│   │       ├── ingestors/
│   │       │   ├── jira_ingestor.py             # Jira REST API fetcher + comments
│   │       │   ├── sharepoint_ingestor.py       # SharePoint online fetcher
│   │       │   └── sharepoint_local_ingestor.py # Local file reader
│   │       ├── notification/
│   │       │   ├── dispatcher.py                # HTML email builder + SMTP sender
│   │       │   └── notification_service.py      # Notification orchestration
│   │       ├── scheduler/
│   │       │   └── ticket_scheduler.py          # APScheduler + multi-agent trigger
│   │       ├── ticket_lifecycle/
│   │       │   ├── auto_closure_service.py      # Legacy auto-closure
│   │       │   └── close_ticket_service.py      # Jira ticket closer
│   │       ├── ingestion_service.py             # FAISS ingest + query engine
│   │       └── rag_service.py                   # RAG orchestration for UI search
│   ├── config_store/
│   │   └── client-a_rag_config.json             # Tenant config (LLM + sources)
│   ├── database/
│   │   ├── migrate.py                           # Creates DB tables
│   │   ├── clear_scheduler.py                   # Utility to clear processed tickets
│   │   └── ticket.db                            # SQLite database (auto-created)
│   ├── faiss_store/                             # FAISS index files (auto-created)
│   ├── .env                                     # Environment variables
│   └── requirements.txt
└── frontend/
    └── src/
        ├── api/
        │   ├── chatApi.js                       # API calls (search, close, ingest)
        │   ├── client.js                        # Axios base client
        │   └── ragAdminApi.js                   # RAG admin API calls
        ├── pages/
        │   ├── ChatPage.jsx                     # Main chat + search UI
        │   ├── LoginPage.jsx                    # Login page
        │   └── RagSetupPage.jsx                 # RAG configuration UI
        └── components/
            ├── DataSourceForm.jsx               # Jira/SharePoint config form
            ├── ModelConfigForm.jsx              # LLM/Embedding config form
            └── SecretConfigForm.jsx             # API keys config form
```

---

## ✨ Features

### Core Features
- **Semantic Search** — Find similar tickets using vector embeddings, not just keyword matching
- **Multi-Source Ingestion** — Ingest from Jira, SharePoint Online, and local SharePoint files
- **Comment Ingestion** — Jira comments (including closure reasons) are fetched and stored
- **Deduplication** — Re-ingesting a ticket updates it instead of creating duplicates
- **Multi-LLM Support** — Switch between OpenAI and Google Gemini via config

### Multi-Agent Automation
- **5 Specialized Agents** — Each with its own LLM reasoning loop
- **Auto-closure** — Tickets with confidence ≥ 0.85 are automatically closed in Jira
- **Auto-escalation** — Low confidence tickets (0.60–0.85) are flagged for human review
- **Smart Notification** — Agent decides priority and sends styled HTML email

### Email Notifications
- **HTML Resolution Table** — Styled table with Source, Ticket ID, Description, Resolution, Confidence
- **New Ticket Summary** — Top box showing new ticket ID, source, and description
- **CC Support** — Send to assignee + additional recipients via `SMTP_CC`
- **Source Type** — Each row shows correct source (Jira / Local SharePoint)

### UI Features
- **Chat Interface** — Search tickets using natural language
- **Results Table** — Shows matched tickets with status, resolution, confidence
- **Open Tickets** — Shown with blank resolution and confidence (not yet resolved)
- **Close Ticket** — Close open tickets from UI using resolution from closed ticket dropdown
- **Auto Refresh** — Table refreshes automatically after closing a ticket
- **Dark/Light Theme** — Toggle between themes
- **RAG Setup** — Configure LLM, embeddings, and data sources from UI

---

## 🔌 API Endpoints

### Chat & Search
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/chat` | Search tickets using RAG (no agent) |

### Agent
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/agent/process-ticket` | Manually trigger multi-agent system |
| `GET` | `/api/v1/agent/status` | Check if LangGraph is available |

### Tickets
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/tickets/close` | Close a ticket in Jira + DB |
| `GET` | `/api/v1/tickets/closed/{tenant_id}` | Get all closed tickets for dropdown |

### RAG Admin
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/admin/rag-config/ingest/{tenant_id}` | Run ingestion pipeline |
| `GET` | `/api/v1/admin/rag-config/{tenant_id}` | Get tenant RAG config |
| `POST` | `/api/v1/admin/rag-config/{tenant_id}` | Save tenant RAG config |

### Auth
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/login` | Login and get session |

### Health
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Health check |

---

## 🚀 Setup & Installation

### Prerequisites
- Python 3.11
- Node.js 18+
- Git

### 1. Clone and setup backend

```bash
cd backend

# Create virtual environment with Python 3.11
py -3.11 -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure environment

```bash
# Copy example env file
cp .env.example .env
```

Edit `.env` with your credentials (see [Configuration](#configuration)).

### 3. Run database migrations

```bash
python database/migrate.py
```

### 4. Start the backend

```bash
python -m uvicorn app.main:app --reload
```

Backend runs at `http://localhost:8000`
Swagger UI at `http://localhost:8000/docs`

### 5. Setup frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`

### 6. Run ingestion

After starting the server, populate the knowledge base:

```
POST http://localhost:8000/api/v1/admin/rag-config/ingest/client-a
```

Or use the RAG Setup page in the UI.

---

## ⚙️ Configuration

### `.env` file

```env
# App
APP_NAME=Ticket Resolution System
APP_ENV=dev

# Auto-closure threshold (0.0 - 1.0)
AUTO_CLOSE_CONFIDENCE_THRESHOLD=0.85

# SMTP Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your_16_char_app_password   # Gmail App Password
SMTP_FROM=your@gmail.com
SMTP_CC=manager@example.com,team@example.com   # optional

# Scheduler
SCHEDULER_ENABLED=true
SCHEDULER_JIRA_INTERVAL_MINUTES=5
SCHEDULER_SHAREPOINT_INTERVAL_MINUTES=5
```

### `config_store/client-a_rag_config.json`

```json
{
  "tenant_id": "client-a",
  "models": {
    "llm_provider": "OpenAI",
    "llm_model_name": "gpt-4o-mini",
    "embedding_provider": "OpenAI",
    "embedding_model_name": "text-embedding-3-small",
    "temperature": 0.1,
    "top_k": 5,
    "max_tokens": 1000,
    "min_confidence": 0.5
  },
  "data_sources": [
    {
      "source_name": "Jira",
      "source_type": "jira",
      "source_url": "https://your-domain.atlassian.net/",
      "username": "your@email.com",
      "token": "your_jira_api_token",
      "project_key": "SCRUM",
      "is_enabled": true
    },
    {
      "source_name": "Local SharePoint",
      "source_type": "sharepoint_local",
      "source_url": "C:\\path\\to\\your\\tickets\\folder",
      "is_enabled": false
    }
  ],
  "secrets": {
    "llm_api_key": "sk-...",
    "embedding_api_key": "sk-..."
  }
}
```

---

## 🔄 How It Works

### UI Search Flow (No Agent)
```
User types query
      ↓
POST /api/v1/chat
      ↓
RAGService.ask() → embeds query → FAISS search → top-k results
      ↓
Results displayed in table:
  - Closed tickets → show resolution + confidence
  - Open tickets   → show blank resolution + blank confidence
```

### New Ticket Auto-Processing Flow (Multi-Agent)
```
APScheduler polls Jira every 5 minutes
      ↓
New ticket detected (not in scheduler_processed table)
      ↓
Coordinator Agent plans execution
      ↓
Ingestion Agent   → check KB age → re-ingest if stale
      ↓
Resolution Agent  → FAISS search → LLM ranks candidates → best match
      ↓
Notification Agent → LLM decides priority → send HTML email
      ↓
Closure Agent     → LLM evaluates confidence:
                    ≥ 0.85 → close ticket in Jira (transition to Done)
                    0.60-0.85 → escalate (record in DB)
                    < 0.60 → skip
      ↓
Coordinator summarizes → ticket marked as processed
```

### Manual Agent Trigger
```
POST /api/v1/agent/process-ticket
{
  "tenant_id": "client-a",
  "ticket_id": "SCRUM-25",
  "source_type": "jira",
  "description": "500 Internal Error on website",
  "assignee_email": "user@example.com"
}
      ↓
Same multi-agent flow as above
      ↓
Returns: decision, confidence, steps_completed, summary
```

### Manual Ticket Close from UI
```
User clicks 🔒 Close on an open ticket row
      ↓
Selects resolution from closed ticket dropdown
      ↓
POST /api/v1/tickets/close
      ↓
CloseTicketService:
  1. Transition Jira ticket to Done
  2. Add comment with resolution
  3. Record in ticket_events DB
      ↓
Trigger re-ingestion (POST /api/v1/admin/rag-config/ingest)
      ↓
Re-run last search → table refreshes automatically
```

---

## 🖥️ UI Guide

### Chat Page
- **Search box** — Type any problem description to find similar resolved tickets
- **Results table** — Shows top matching tickets with confidence scores
- **Close button** — Appears on open tickets only (not on Done/Closed rows)
- **Close dialog** — Select resolution from closed ticket dropdown, ticket ID pre-filled

### RAG Setup Page (⚙ button)
- **Model Config** — Set LLM provider, model, temperature
- **Data Sources** — Configure Jira URL, credentials, project key
- **Ingestion** — Trigger manual re-ingestion of knowledge base
- **Test Connection** — Verify Jira/SharePoint connectivity

---

## 🗄️ Database Tables

```sql
-- Tracks scheduler processed tickets (prevents duplicate processing)
scheduler_processed (id, tenant_id, source_type, ticket_id, content_hash, processed_at)

-- Records all ticket lifecycle events (auto-close, escalate, notified)
ticket_events (id, tenant_id, ticket_id, source_type, event_type,
               confidence, matched_ticket_id, resolution, reason, created_at)

-- Logs all outgoing notifications
notification_log (id, tenant_id, ticket_id, assignee_email, channel,
                  status, payload, error_message, created_at)

-- User sessions
sessions (session_id, username, created_at, expires_at)

-- Users
users (id, username, password_hash, created_at)
```

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
    description='500 Internal Error on website after deployment',
    assignee_email='your@email.com',
)
print(result)
"
```

### Clear scheduler cache (reprocess tickets)
```bash
python database/clear_scheduler.py --all
python database/clear_scheduler.py --ticket SCRUM-9
```

### Check DB contents
```bash
python -c "
import sqlite3
from app.core.db_path import get_db_path
conn = sqlite3.connect(get_db_path())
print([r for r in conn.execute('SELECT ticket_id, event_type, confidence FROM ticket_events ORDER BY created_at DESC LIMIT 10')])
"
```