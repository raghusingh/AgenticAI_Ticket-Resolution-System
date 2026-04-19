"""
services/agent/agent_tools.py

LangChain tools that wrap existing services.
The LangGraph agent calls these tools autonomously based on LLM reasoning.

Tools:
  - search_rag          → finds matching resolutions from vector DB
  - send_resolution_email → sends HTML resolution table to assignee
  - close_jira_ticket   → closes ticket in Jira + records in DB
  - escalate_ticket     → logs escalation event for human review
  - ask_clarification   → returns a clarifying question to the log
"""

import json
import logging
from typing import Optional
from langchain.tools import tool

logger = logging.getLogger(__name__)


# ── Tool 1: Search RAG ────────────────────────────────────────────────────────

@tool
def search_rag(input_json: str) -> str:
    """
    Search the RAG vector database for tickets similar to the given description.
    Input must be a JSON string with keys: tenant_id (str), description (str), top_k (int, optional).
    Returns a JSON string with matching tickets and confidence scores.
    Use this tool first when a new ticket arrives to find similar resolved tickets.
    """
    try:
        data = json.loads(input_json)
        tenant_id   = data.get("tenant_id", "")
        description = data.get("description", "")
        top_k       = int(data.get("top_k", 5))

        from app.repositories.rag_admin_repository import RagAdminRepository
        from app.services.ingestion_service import IngestionService

        repo   = RagAdminRepository()
        svc    = IngestionService(repo)
        result = svc.query(tenant_id, description, top_k=top_k)
        tickets = result.get("tickets", [])

        print(f"[Tool:search_rag] Found {len(tickets)} match(es) for tenant={tenant_id}")

        return json.dumps({
            "status": "success",
            "ticket_count": len(tickets),
            "tickets": tickets[:top_k],
        })

    except Exception as exc:
        logger.error("[Tool:search_rag] Error: %s", exc)
        return json.dumps({"status": "error", "message": str(exc), "tickets": []})


# ── Tool 2: Send Resolution Email ─────────────────────────────────────────────

@tool
def send_resolution_email(input_json: str) -> str:
    """
    Send a resolution suggestion email to the ticket assignee.
    Input must be a JSON string with keys:
      tenant_id (str), ticket_id (str), source_type (str),
      description (str), assignee_email (str), tickets (list of dicts).
    Use this tool after search_rag returns results to notify the assignee.
    """
    try:
        data = json.loads(input_json)

        from app.schemas.notification import NotifyRequest
        from app.services.notification.notification_service import NotificationService

        result = NotificationService().notify_on_ticket_created(
            NotifyRequest(
                tenant_id       = data.get("tenant_id", ""),
                ticket_id       = data.get("ticket_id", ""),
                source_type     = data.get("source_type", ""),
                description     = data.get("description", ""),
                assignee_email  = data.get("assignee_email"),
                top_k           = 5,
                prefetched_tickets = data.get("tickets", []),
            )
        )

        print(f"[Tool:send_email] channel={result.channel} status={result.status}")

        return json.dumps({
            "status": result.status,
            "channel": result.channel,
            "message": result.message,
            "resolutions_sent": len(result.resolutions),
        })

    except Exception as exc:
        logger.error("[Tool:send_email] Error: %s", exc)
        return json.dumps({"status": "error", "message": str(exc)})


# ── Tool 3: Close Jira Ticket ─────────────────────────────────────────────────

@tool
def close_jira_ticket(input_json: str) -> str:
    """
    Close a ticket in Jira and record the closure in the local database.
    Input must be a JSON string with keys:
      tenant_id (str), ticket_id (str), reason (str).
    Use this tool only when confidence is high (>= 0.85) and the ticket
    clearly matches a known resolution. Do NOT close if confidence is low.
    """
    try:
        data      = json.loads(input_json)
        tenant_id = data.get("tenant_id", "")
        ticket_id = data.get("ticket_id", "")
        reason    = data.get("reason", "Auto-closed by agent based on high confidence match.")

        from app.services.ticket_lifecycle.close_ticket_service import CloseTicketService

        result = CloseTicketService().close(
            tenant_id=tenant_id,
            ticket_id=ticket_id,
            reason=reason,
        )

        print(f"[Tool:close_ticket] status={result['status']} jira_updated={result['jira_updated']}")

        return json.dumps(result)

    except Exception as exc:
        logger.error("[Tool:close_ticket] Error: %s", exc)
        return json.dumps({"status": "error", "message": str(exc)})


# ── Tool 4: Escalate Ticket ───────────────────────────────────────────────────

@tool
def escalate_ticket(input_json: str) -> str:
    """
    Escalate a ticket for human review when confidence is too low to auto-close
    or when the issue is too complex for automated resolution.
    Input must be a JSON string with keys:
      tenant_id (str), ticket_id (str), source_type (str), reason (str).
    Use this tool when confidence < 0.85 or when no good match is found.
    """
    try:
        data       = json.loads(input_json)
        tenant_id  = data.get("tenant_id", "")
        ticket_id  = data.get("ticket_id", "")
        source_type = data.get("source_type", "jira")
        reason     = data.get("reason", "Low confidence — requires human review.")

        from app.repositories.ticket_lifecycle_repository import TicketLifecycleRepository

        repo = TicketLifecycleRepository()
        repo.record_event(
            tenant_id   = tenant_id,
            ticket_id   = ticket_id,
            source_type = source_type,
            event_type  = "escalated",
            reason      = reason,
        )

        print(f"[Tool:escalate] Ticket {ticket_id} escalated — {reason}")

        return json.dumps({
            "status": "escalated",
            "ticket_id": ticket_id,
            "reason": reason,
            "message": f"Ticket {ticket_id} flagged for human review.",
        })

    except Exception as exc:
        logger.error("[Tool:escalate] Error: %s", exc)
        return json.dumps({"status": "error", "message": str(exc)})


# ── Tool 5: Ask Clarification ─────────────────────────────────────────────────

@tool
def ask_clarification(input_json: str) -> str:
    """
    Log a clarifying question when the ticket description is too vague
    to search or resolve confidently.
    Input must be a JSON string with keys:
      ticket_id (str), question (str).
    Use this tool when the description is under 20 words or lacks
    enough technical detail to search the knowledge base effectively.
    """
    try:
        data      = json.loads(input_json)
        ticket_id = data.get("ticket_id", "")
        question  = data.get("question", "")

        print(f"[Tool:clarify] Ticket {ticket_id} — Question: {question}")

        return json.dumps({
            "status": "clarification_requested",
            "ticket_id": ticket_id,
            "question": question,
            "message": f"Clarification logged for ticket {ticket_id}.",
        })

    except Exception as exc:
        logger.error("[Tool:clarify] Error: %s", exc)
        return json.dumps({"status": "error", "message": str(exc)})


# ── Tool registry ─────────────────────────────────────────────────────────────

AGENT_TOOLS = [
    search_rag,
    send_resolution_email,
    close_jira_ticket,
    escalate_ticket,
    ask_clarification,
]
