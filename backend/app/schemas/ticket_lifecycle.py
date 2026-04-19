from typing import Optional
from pydantic import BaseModel


class AutoCloseRequest(BaseModel):
    """
    Request body for the auto-closure endpoint.
    The caller provides a new ticket's details; the service
    searches for a best match and decides whether to close it.
    """
    tenant_id: str
    ticket_id: str
    source_type: str                        # 'jira' | 'sharepoint_local'
    description: str                        # new ticket's problem statement
    assignee_email: Optional[str] = None
    confidence_threshold: Optional[float] = 0.85   # default close threshold


class AutoCloseResult(BaseModel):
    ticket_id: str
    auto_closed: bool
    confidence_score: float
    matched_ticket_id: Optional[str] = None
    resolution: Optional[str] = None
    root_cause: Optional[str] = None
    reason: str                             # human-readable explanation
