from typing import Dict, List, Optional
from pydantic import BaseModel


class ResolutionRow(BaseModel):
    """One row in the resolution table sent to the assignee."""
    ticket_id: str = ""
    ticket_description: str = ""
    resolution: str = ""
    root_cause: str = ""
    issue_type: str = ""
    status: str = ""
    priority: str = ""
    confidence_score: float = 0.0
    source_url: Optional[str] = None
    source_type: str = ""          # ✅ source of the matched resolution row


class NotifyRequest(BaseModel):
    """
    Trigger a resolution notification for a newly created ticket.
    Pass prefetched_tickets (already found by the Scheduler's RAG call)
    to skip the duplicate RAG search inside NotificationService.
    """
    tenant_id: str
    ticket_id: str
    source_type: str                              # 'jira' | 'sharepoint_local'
    description: str                              # new ticket problem statement
    assignee_email: Optional[str] = None
    top_k: Optional[int] = 5
    prefetched_tickets: Optional[List[Dict]] = None  # ← RAG results from Scheduler


class NotifyResult(BaseModel):
    ticket_id: str
    assignee_email: Optional[str]
    channel: str                                  # 'email' | 'mock'
    status: str                                   # 'sent' | 'failed' | 'mock_sent'
    resolutions: List[ResolutionRow] = []
    message: str
