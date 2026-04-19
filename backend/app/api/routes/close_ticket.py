"""
api/routes/close_ticket.py

POST /api/v1/tickets/close
  - Closes a Jira ticket (transitions to Done)
  - Adds a comment to the ticket
  - Records closure event in local DB
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.ticket_lifecycle.close_ticket_service import CloseTicketService

router = APIRouter(prefix="/api/v1/tickets", tags=["Tickets"])


class CloseTicketRequest(BaseModel):
    tenant_id: str
    ticket_id: str
    reason: Optional[str] = "Manually closed via API."


class CloseTicketResponse(BaseModel):
    ticket_id: str
    status: str          # 'closed' | 'skipped' | 'failed'
    message: str
    jira_updated: bool
    reason: Optional[str] = None


@router.post("/close", response_model=CloseTicketResponse)
def close_ticket(request: CloseTicketRequest):
    """
    Manually close a ticket in both Jira and the local database.

    - Transitions the Jira ticket to **Done**
    - Adds a comment with the reason
    - Records a closure event in `ticket_events` table

    Example:
    ```json
    {
        "tenant_id": "client-a",
        "ticket_id": "SCRUM-20",
        "reason": "Issue resolved by infra team."
    }
    ```
    """
    try:
        service = CloseTicketService()
        result = service.close(
            tenant_id=request.tenant_id,
            ticket_id=request.ticket_id,
            reason=request.reason or "Manually closed via API.",
        )

        if result["status"] == "failed":
            raise HTTPException(status_code=400, detail=result["message"])

        return CloseTicketResponse(**result)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
