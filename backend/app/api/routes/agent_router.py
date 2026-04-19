"""
api/routes/agent_router.py

POST /api/v1/agent/process-ticket  — manually trigger the LangGraph agent
GET  /api/v1/agent/status          — check if agent is available
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

router = APIRouter(prefix="/api/v1/agent", tags=["Agent"])


class AgentTicketRequest(BaseModel):
    tenant_id:      str
    ticket_id:      str
    source_type:    str = "jira"
    description:    str
    assignee_email: Optional[str] = None


class AgentActionStep(BaseModel):
    tool:   str
    status: str


class AgentTicketResponse(BaseModel):
    ticket_id:       str
    decision:        str          # 'closed' | 'escalated' | 'notified' | 'clarification_needed'
    summary:         str
    best_confidence: float
    steps_taken:     int
    action_history:  List[AgentActionStep]


@router.post("/process-ticket", response_model=AgentTicketResponse)
def process_ticket_with_agent(request: AgentTicketRequest):
    """
    Manually trigger the LangGraph agent to process a ticket.

    The agent will autonomously:
    1. Search the RAG knowledge base
    2. Send a resolution email to the assignee
    3. Close the ticket in Jira (if confidence >= threshold)
       OR escalate for human review (if confidence < threshold)

    Example:
    ```json
    {
        "tenant_id": "client-a",
        "ticket_id": "SCRUM-25",
        "source_type": "jira",
        "description": "500 Internal Error on website after deployment",
        "assignee_email": "user@example.com"
    }
    ```
    """
    try:
        from app.services.agent.ticket_agent import run_ticket_agent

        result = run_ticket_agent(
            tenant_id      = request.tenant_id,
            ticket_id      = request.ticket_id,
            source_type    = request.source_type,
            description    = request.description,
            assignee_email = request.assignee_email,
        )

        return AgentTicketResponse(
            ticket_id       = result["ticket_id"],
            decision        = result["decision"],
            summary         = result["summary"],
            best_confidence = result["best_confidence"],
            steps_taken     = result["steps_taken"],
            action_history  = [
                AgentActionStep(tool=a["tool"], status=a["status"])
                for a in result["action_history"]
            ],
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/status")
def agent_status():
    """Check if the LangGraph agent is available."""
    try:
        import langgraph
        import langchain
        return {
            "status":     "available",
            "langgraph":  langgraph.__version__,
            "langchain":  langchain.__version__,
        }
    except ImportError as exc:
        return {
            "status":  "unavailable",
            "reason":  str(exc),
            "fix":     "pip install langgraph langchain langchain-openai",
        }
