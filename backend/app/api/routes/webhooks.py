"""
api/routes/webhooks.py

Jira / SharePoint webhook receiver.

When a new ticket is created in Jira or SharePoint, they can POST to:

  POST /api/v1/webhooks/jira
  POST /api/v1/webhooks/sharepoint

The handler will:
  1. Parse the incoming event payload.
  2. Call NotificationService  → send resolution table to assignee.
  3. Call AutoClosureService   → evaluate and record closure decision.
  4. Return a combined result.

Jira webhook setup
------------------
In your Jira project → Project Settings → Webhooks → Create webhook:
  URL: https://your-server/api/v1/webhooks/jira?tenant_id=client-a
  Events: Issue Created

SharePoint Power Automate
-------------------------
Use a Power Automate flow triggered on "When an item is created" in your
SharePoint list. Add an HTTP action that POSTs to:
  URL: https://your-server/api/v1/webhooks/sharepoint?tenant_id=client-a
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request

from app.schemas.notification import NotifyRequest
from app.schemas.ticket_lifecycle import AutoCloseRequest
from app.services.notification.notification_service import NotificationService
from app.services.ticket_lifecycle.auto_closure_service import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    AutoClosureService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


# ── Jira ──────────────────────────────────────────────────────────────────────

@router.post("/jira")
async def jira_webhook(
    request: Request,
    tenant_id: str = Query(..., description="Tenant ID, e.g. client-a"),
):
    """
    Receives Jira 'issue_created' webhook events.
    Automatically triggers resolution notification + auto-closure evaluation.
    """
    body: Dict[str, Any] = await request.json()

    event_type = body.get("webhookEvent", "")
    if event_type not in ("jira:issue_created", "issue_created", ""):
        return {"status": "ignored", "reason": f"Event '{event_type}' not handled."}

    issue = body.get("issue", {})
    fields = issue.get("fields", {})

    ticket_id = issue.get("key", "UNKNOWN")
    summary = fields.get("summary", "")
    description_obj = fields.get("description", {})

    # Jira description can be ADF (Atlassian Document Format) or plain text
    description_text = _extract_jira_description(description_obj) or summary

    assignee = fields.get("assignee") or {}
    assignee_email: Optional[str] = assignee.get("emailAddress")

    logger.info("Jira webhook received: ticket=%s tenant=%s", ticket_id, tenant_id)

    return _process_ticket(
        tenant_id=tenant_id,
        ticket_id=ticket_id,
        source_type="jira",
        description=description_text,
        assignee_email=assignee_email,
    )


# ── SharePoint ────────────────────────────────────────────────────────────────

@router.post("/sharepoint")
async def sharepoint_webhook(
    request: Request,
    tenant_id: str = Query(..., description="Tenant ID, e.g. client-a"),
):
    """
    Receives SharePoint Power Automate HTTP POST events.
    Payload should contain: ticket_id, description, assignee_email (all strings).

    Example Power Automate body:
    {
        "ticket_id": "SP-001",
        "description": "Login fails after password reset",
        "assignee_email": "support@company.com"
    }
    """
    body: Dict[str, Any] = await request.json()

    ticket_id = str(body.get("ticket_id") or body.get("id") or "SP-UNKNOWN")
    description = str(body.get("description") or body.get("title") or "")
    assignee_email = body.get("assignee_email") or body.get("email")

    logger.info("SharePoint webhook received: ticket=%s tenant=%s", ticket_id, tenant_id)

    return _process_ticket(
        tenant_id=tenant_id,
        ticket_id=ticket_id,
        source_type="sharepoint_local",
        description=description,
        assignee_email=assignee_email,
    )


# ── Shared processor ─────────────────────────────────────────────────────────

def _process_ticket(
    tenant_id: str,
    ticket_id: str,
    source_type: str,
    description: str,
    assignee_email: Optional[str],
) -> dict:
    """
    Runs notification + auto-closure in sequence and returns combined result.
    Both are run regardless of each other's outcome.
    """
    # 1️⃣  Send resolution notification to assignee
    notification_result = NotificationService().notify_on_ticket_created(
        NotifyRequest(
            tenant_id=tenant_id,
            ticket_id=ticket_id,
            source_type=source_type,
            description=description,
            assignee_email=assignee_email,
        )
    )

    # 2️⃣  Evaluate auto-closure
    closure_result = AutoClosureService().evaluate(
        AutoCloseRequest(
            tenant_id=tenant_id,
            ticket_id=ticket_id,
            source_type=source_type,
            description=description,
            assignee_email=assignee_email,
            confidence_threshold=DEFAULT_CONFIDENCE_THRESHOLD,
        )
    )

    return {
        "ticket_id": ticket_id,
        "tenant_id": tenant_id,
        "notification": {
            "status": notification_result.status,
            "channel": notification_result.channel,
            "message": notification_result.message,
        },
        "auto_closure": {
            "auto_closed": closure_result.auto_closed,
            "confidence_score": closure_result.confidence_score,
            "matched_ticket_id": closure_result.matched_ticket_id,
            "resolution": closure_result.resolution,
            "reason": closure_result.reason,
        },
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_jira_description(description_obj: Any) -> str:
    """
    Jira descriptions are ADF (Atlassian Document Format) JSON objects.
    This walks the content tree and extracts plain text.
    Falls back gracefully if the description is already a string.
    """
    if isinstance(description_obj, str):
        return description_obj

    if not isinstance(description_obj, dict):
        return ""

    texts = []

    def _walk(node: Any):
        if isinstance(node, dict):
            if node.get("type") == "text":
                texts.append(node.get("text", ""))
            for child in node.get("content", []):
                _walk(child)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(description_obj)
    return " ".join(t for t in texts if t).strip()
