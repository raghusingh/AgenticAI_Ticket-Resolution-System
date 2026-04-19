from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.chat import router as chat_router
from app.api.routes.config import router as config_router
from app.api.routes.theme import router as theme_router
from app.api.routes.health import router as health_router
from app.api.routes.rag_admin import router as rag_admin_router
from app.api.routes.ticket_lifecycle import router as ticket_lifecycle_router
from app.api.routes.notification import router as notification_router
from app.api.routes.scheduler import router as scheduler_router
from app.api.routes.webhooks import router as webhooks_router
from app.api.routes.close_ticket import router as close_ticket_router
from app.api.routes.agent_router import router as agent_router
from app.core.settings import settings
from app.api.auth import router as auth_router
from database.migrate import migrate
from app.services.scheduler.ticket_scheduler import start_scheduler, stop_scheduler

app = FastAPI(
    title=settings.app_name,
    version="1.3.0",
    description="RAG-based Ticket Resolution System with auto-closure, notifications and scheduler.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    # Run DB migrations (idempotent)
    migrate()
    # Start background scheduler
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    stop_scheduler()


# ── Existing routers ──────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(config_router)
app.include_router(theme_router)
app.include_router(health_router)
app.include_router(rag_admin_router)

# ── New feature routers ───────────────────────────────────────────────────────
app.include_router(ticket_lifecycle_router)
app.include_router(notification_router)
app.include_router(webhooks_router)
app.include_router(scheduler_router)
app.include_router(close_ticket_router)
app.include_router(agent_router)