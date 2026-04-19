"""
api/routes/ticket_lifecycle.py

Endpoints
---------
POST /api/v1/tickets/auto-close
    Evaluate whether a new ticket should be auto-closed.

GET  /api/v1/tickets/events/{tenant_id}
    List recent ticket closure events for a tenant.
"""

from fastapi import APIRouter, HTTPException

from app.repositories.ticket_lifecycle_repository import TicketLifecycleRepository
from app.schemas.ticket_lifecycle import AutoCloseRequest, AutoCloseResult
from app.services.ticket_lifecycle.auto_closure_service import AutoClosureService

router = APIRouter(prefix="/api/v1/tickets", tags=["ticket-lifecycle"])


@router.post("/auto-close", response_model=AutoCloseResult)
def auto_close_ticket(request: AutoCloseRequest):
    """
    Accepts a new ticket's details, queries the RAG knowledge base,
    and returns an auto-closure decision.

    If `auto_closed` is True the caller should update the ticket's
    status in Jira / SharePoint accordingly using the returned
    `resolution` and `matched_ticket_id`.
    """
    service = AutoClosureService()
    result = service.evaluate(request)
    return result


@router.get("/events/{tenant_id}")
def list_ticket_events(tenant_id: str, limit: int = 50):
    """
    Returns the most recent auto-closure events for a tenant.
    Useful for audit dashboards and debugging.
    """
    repo = TicketLifecycleRepository()
    events = repo.list_events(tenant_id, limit=limit)
    return {"tenant_id": tenant_id, "events": events}
