"""
services/agent/agents/closure_agent.py

Closure Agent — specialized agent that handles ticket closure decisions.

Responsibilities:
  - Evaluate confidence score against threshold
  - Decide: auto-close, escalate, or skip
  - Execute closure in Jira if decided
  - Record decision in DB

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

CLOSURE_SYSTEM_PROMPT = """You are a Closure Agent responsible for deciding whether to auto-close support tickets.

Decision rules:
1. confidence >= 0.85 AND resolution exists → AUTO-CLOSE the ticket
2. confidence >= 0.60 AND < 0.85 → ESCALATE for human review (good match but not confident enough)
3. confidence < 0.60 OR no resolution → SKIP (not enough info to act)
4. Already closed → SKIP

Be conservative — only close when truly confident.

Respond with JSON only:
{
  "decision": "close" | "escalate" | "skip",
  "reason": "clear explanation of your decision",
  "confidence_used": 0.0
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


def _close_ticket(tenant_id: str, ticket_id: str, reason: str) -> dict:
    """Close ticket in Jira and record in DB."""
    try:
        from app.services.ticket_lifecycle.close_ticket_service import CloseTicketService
        return CloseTicketService().close(
            tenant_id=tenant_id,
            ticket_id=ticket_id,
            reason=reason,
        )
    except Exception as exc:
        logger.error("[ClosureAgent] Close failed: %s", exc)
        return {"status": "failed", "message": str(exc)}


def _escalate_ticket(tenant_id: str, ticket_id: str,
                     source_type: str, reason: str) -> dict:
    """Record escalation event in DB."""
    try:
        from app.repositories.ticket_lifecycle_repository import TicketLifecycleRepository
        repo = TicketLifecycleRepository()
        repo.record_event(
            tenant_id=tenant_id,
            ticket_id=ticket_id,
            source_type=source_type,
            event_type="escalated",
            reason=reason,
        )
        return {"status": "escalated", "message": reason}
    except Exception as exc:
        logger.error("[ClosureAgent] Escalation record failed: %s", exc)
        return {"status": "failed", "message": str(exc)}


# ── Agent nodes ───────────────────────────────────────────────────────────────

def reason_node(state: TicketState) -> TicketState:
    """LLM decides whether to close, escalate or skip."""
    print(f"[ClosureAgent] 🧠 Reasoning about closure decision...")

    context = {
        "ticket_id": state["ticket_id"],
        "description": state["description"][:200],
        "resolution_status": state.get("resolution_status"),
        "best_confidence": state.get("best_confidence", 0),
        "best_resolution": state.get("best_resolution", "")[:200],
        "best_matched_ticket": state.get("best_ticket_id"),
        "confidence_threshold": 0.85,
    }

    llm = _get_llm(state["tenant_id"])
    response = llm.invoke([
        SystemMessage(content=CLOSURE_SYSTEM_PROMPT),
        HumanMessage(content=f"Ticket context:\n{json.dumps(context, indent=2)}\n\nWhat should I do?"),
    ])

    raw = response.content.strip().strip("```json").strip("```").strip()
    try:
        decision = json.loads(raw)
    except Exception:
        decision = {
            "decision": "skip",
            "reason": "Could not parse LLM response — defaulting to skip",
            "confidence_used": state.get("best_confidence", 0),
        }

    print(f"[ClosureAgent] Decision: {decision['decision']} — {decision['reason']}")
    return {**state, "_closure_decision": decision}


def act_node(state: TicketState) -> TicketState:
    """Execute the closure decision."""
    decision = state.get("_closure_decision", {})
    action = decision.get("decision", "skip")
    reason = decision.get("reason", "")
    confidence = float(decision.get("confidence_used", state.get("best_confidence", 0)))

    if action == "close":
        print(f"[ClosureAgent] 🔒 Closing ticket {state['ticket_id']}...")
        result = _close_ticket(
            tenant_id=state["tenant_id"],
            ticket_id=state["ticket_id"],
            reason=state.get("best_resolution") or reason,
        )
        closure_decision = "closed" if result.get("status") != "failed" else "failed"

    elif action == "escalate":
        print(f"[ClosureAgent] 🚨 Escalating ticket {state['ticket_id']}...")
        _escalate_ticket(
            tenant_id=state["tenant_id"],
            ticket_id=state["ticket_id"],
            source_type=state["source_type"],
            reason=reason,
        )
        closure_decision = "escalated"

    else:
        print(f"[ClosureAgent] ⏭️  Skipping closure for {state['ticket_id']}")
        closure_decision = "skipped"

    steps = state.get("steps_completed", []) + ["closure"]
    return {
        **state,
        "closure_decision": closure_decision,
        "closure_reason": reason,
        "closure_confidence": confidence,
        "steps_completed": steps,
    }


# ── Build graph ───────────────────────────────────────────────────────────────

def build_closure_agent():
    graph = StateGraph(TicketState)
    graph.add_node("reason", reason_node)
    graph.add_node("act", act_node)
    graph.set_entry_point("reason")
    graph.add_edge("reason", "act")
    graph.add_edge("act", END)
    return graph.compile()


def run_closure_agent(state: TicketState) -> TicketState:
    """Entry point called by coordinator."""
    print(f"\n[ClosureAgent] 🚀 Starting for ticket={state['ticket_id']}")
    graph = build_closure_agent()
    result = graph.invoke(state)
    print(f"[ClosureAgent] ✅ Done — decision={result['closure_decision']}")
    return result