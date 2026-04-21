"""
services/agent/agents/agent_state.py

Shared state passed between all agents in the multi-agent system.
Each agent reads from and writes to this state.
"""

from typing import Any, Dict, List, Optional, TypedDict


class TicketState(TypedDict):
    """Shared state passed through the multi-agent pipeline."""

    # ── Input context ─────────────────────────────────────────────────────────
    tenant_id:       str
    ticket_id:       str
    source_type:     str
    description:     str
    assignee_email:  Optional[str]

    # ── Ingestion Agent output ────────────────────────────────────────────────
    ingestion_status:   str    # 'fresh' | 'refreshed' | 'failed' | 'skipped'
    ingestion_message:  str

    # ── Resolution Agent output ───────────────────────────────────────────────
    rag_tickets:        List[Dict[str, Any]]   # matched tickets from FAISS
    best_confidence:    float
    best_resolution:    str
    best_ticket_id:     str
    resolution_status:  str    # 'found' | 'not_found' | 'failed'

    # ── Notification Agent output ─────────────────────────────────────────────
    notification_status:  str   # 'sent' | 'mock_sent' | 'failed' | 'skipped'
    notification_channel: str   # 'email' | 'mock'
    notification_message: str

    # ── Closure Agent output ──────────────────────────────────────────────────
    closure_decision:   str    # 'closed' | 'escalated' | 'skipped'
    closure_reason:     str
    closure_confidence: float

    # ── Coordinator tracking ──────────────────────────────────────────────────
    steps_completed:    List[str]   # which agents have run
    errors:             List[str]   # any errors encountered
    final_summary:      str
    done:               bool


def initial_state(
    tenant_id: str,
    ticket_id: str,
    source_type: str,
    description: str,
    assignee_email: Optional[str] = None,
) -> TicketState:
    """Create initial empty state for a new ticket."""
    return TicketState(
        tenant_id=tenant_id,
        ticket_id=ticket_id,
        source_type=source_type,
        description=description,
        assignee_email=assignee_email,

        ingestion_status="",
        ingestion_message="",

        rag_tickets=[],
        best_confidence=0.0,
        best_resolution="",
        best_ticket_id="",
        resolution_status="",

        notification_status="",
        notification_channel="",
        notification_message="",

        closure_decision="",
        closure_reason="",
        closure_confidence=0.0,

        steps_completed=[],
        errors=[],
        final_summary="",
        done=False,
    )