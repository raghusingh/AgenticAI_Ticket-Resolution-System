"""
services/agent/agents/notification_agent.py

Notification Agent — specialized agent that handles all notifications.

Responsibilities:
  - Decide whether to send notification based on resolution results
  - Build resolution table from matched tickets
  - Send email to assignee (+ CC)
  - Log notification result

This agent has its OWN LLM reasoning loop.
"""

import json
import logging
import os
from pathlib import Path

from langchain.schema import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from app.services.agent.agents.agent_state import TicketState

logger = logging.getLogger(__name__)

NOTIFICATION_SYSTEM_PROMPT = """You are a Notification Agent responsible for sending resolution suggestions to ticket assignees.

Your job is to decide:
1. Should a notification be sent? (yes if there are any results, even partial)
2. What priority level is this? (high if confidence >= 0.85, normal otherwise)

Rules:
- Always send notification if there are matching tickets (even open ones)
- Skip notification only if there are zero results AND no assignee email
- If no assignee email provided, use mock/log mode

Respond with JSON only:
{
  "should_notify": true | false,
  "priority": "high" | "normal",
  "reason": "brief reason"
}
"""


def _get_llm(tenant_id: str):
    config_path = (
        Path(__file__).resolve().parents[4]
        / "config_store"
        / f"{tenant_id}_rag_config.json"
    )
    provider = "openai"
    model_name = "gpt-4o-mini"
    api_key = os.getenv("OPENAI_API_KEY", "")

    if config_path.exists():
        with open(config_path) as f:
            raw = json.load(f)
        models = raw.get("models", {})
        secrets = raw.get("secrets", {})
        provider = (models.get("llm_provider") or "openai").lower()
        model_name = models.get("llm_model_name") or model_name
        api_key = secrets.get("llm_api_key") or ""

    if provider in ("openai",):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model_name, api_key=api_key, temperature=0)
    elif provider in ("google", "gemini"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model_name, google_api_key=api_key,
            temperature=0, convert_system_message_to_human=True
        )
    raise ValueError(f"Unsupported provider: {provider}")


def _send_notification(state: TicketState) -> dict:
    """Send notification using existing NotificationService."""
    try:
        from app.schemas.notification import NotifyRequest
        from app.services.notification.notification_service import NotificationService

        result = NotificationService().notify_on_ticket_created(
            NotifyRequest(
                tenant_id=state["tenant_id"],
                ticket_id=state["ticket_id"],
                source_type=state["source_type"],
                description=state["description"],
                assignee_email=state.get("assignee_email"),
                top_k=5,
                prefetched_tickets=state.get("rag_tickets", []),
            )
        )
        return {
            "status": result.status,
            "channel": result.channel,
            "message": result.message,
        }
    except Exception as exc:
        logger.error("[NotificationAgent] Send failed: %s", exc)
        return {"status": "failed", "channel": "none", "message": str(exc)}


# ── Agent nodes ───────────────────────────────────────────────────────────────

def reason_node(state: TicketState) -> TicketState:
    """LLM decides whether and how to notify."""
    print(f"[NotificationAgent] 🧠 Reasoning about notification...")

    context = {
        "ticket_id": state["ticket_id"],
        "assignee_email": state.get("assignee_email"),
        "resolution_status": state.get("resolution_status"),
        "matches_found": len(state.get("rag_tickets", [])),
        "best_confidence": state.get("best_confidence", 0),
    }

    llm = _get_llm(state["tenant_id"])
    response = llm.invoke([
        SystemMessage(content=NOTIFICATION_SYSTEM_PROMPT),
        HumanMessage(content=f"Context:\n{json.dumps(context, indent=2)}\n\nShould I notify?"),
    ])

    raw = response.content.strip().strip("```json").strip("```").strip()
    try:
        decision = json.loads(raw)
    except Exception:
        decision = {"should_notify": True, "priority": "normal", "reason": "Default"}

    print(f"[NotificationAgent] Decision: notify={decision['should_notify']} "
          f"priority={decision['priority']}")
    return {**state, "_should_notify": decision["should_notify"],
            "_notify_priority": decision["priority"]}


def act_node(state: TicketState) -> TicketState:
    """Send notification if decided."""
    should_notify = state.get("_should_notify", True)

    if should_notify:
        print(f"[NotificationAgent] 📧 Sending notification for {state['ticket_id']}...")
        result = _send_notification(state)
        status = result["status"]
        channel = result["channel"]
        message = result["message"]
    else:
        print(f"[NotificationAgent] ⏭️  Skipping notification")
        status = "skipped"
        channel = "none"
        message = "Notification skipped — no results to send"

    steps = state.get("steps_completed", []) + ["notification"]
    return {
        **state,
        "notification_status": status,
        "notification_channel": channel,
        "notification_message": message,
        "steps_completed": steps,
    }


# ── Build graph ───────────────────────────────────────────────────────────────

def build_notification_agent():
    graph = StateGraph(TicketState)
    graph.add_node("reason", reason_node)
    graph.add_node("act", act_node)
    graph.set_entry_point("reason")
    graph.add_edge("reason", "act")
    graph.add_edge("act", END)
    return graph.compile()


def run_notification_agent(state: TicketState) -> TicketState:
    """Entry point called by coordinator."""
    print(f"\n[NotificationAgent] 🚀 Starting for ticket={state['ticket_id']}")
    graph = build_notification_agent()
    result = graph.invoke(state)
    print(f"[NotificationAgent] ✅ Done — status={result['notification_status']}")
    return result