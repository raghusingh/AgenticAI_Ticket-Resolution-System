"""
api/routes/notification.py

Endpoints
---------
POST /api/v1/notifications/send
    Trigger a resolution notification for a new ticket.
    Called by Jira / SharePoint webhook handlers or manually.

GET  /api/v1/notifications/log/{tenant_id}
    List recent notification log entries for a tenant.
"""

from fastapi import APIRouter

from app.repositories.ticket_lifecycle_repository import TicketLifecycleRepository
from app.schemas.notification import NotifyRequest, NotifyResult
from app.services.notification.notification_service import NotificationService

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.post("/send", response_model=NotifyResult)
def send_resolution_notification(request: NotifyRequest):
    """
    Queries the RAG knowledge base for resolution matches and
    dispatches an HTML table notification to the ticket assignee.

    Works in two modes
    ------------------
    - **Email mode** (when SMTP_HOST, SMTP_USER, SMTP_PASSWORD are set in .env)
    - **Mock/log mode** (default when SMTP is not configured) — logs to console,
      ideal for development / demo.
    """
    service = NotificationService()
    return service.notify_on_ticket_created(request)


@router.get("/log/{tenant_id}")
def list_notification_log(tenant_id: str, limit: int = 50):
    """
    Returns the notification history for a tenant.
    Includes channel, status, and when each notification was sent.
    """
    repo = TicketLifecycleRepository()
    logs = repo.list_notifications(tenant_id, limit=limit)
    return {"tenant_id": tenant_id, "notifications": logs}
