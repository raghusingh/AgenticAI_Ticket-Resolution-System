"""
services/agent/agents/coordinator_agent.py

Coordinator Agent — the brain of the multi-agent system.

Responsibilities:
  - Receive new ticket
  - Plan which agents to run and in what order
  - Invoke each specialized agent sequentially
  - Handle failures gracefully (one agent fails → others still run)
  - Compile final summary

Agent execution order:
  1. IngestionAgent   → ensure KB is fresh
  2. ResolutionAgent  → find best matching resolution
  3. NotificationAgent → notify assignee
  4. ClosureAgent     → close or escalate ticket

This coordinator has its OWN LLM for high-level planning.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

from langchain.schema import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from app.services.agent.agents.agent_state import TicketState, initial_state
from app.services.agent.agents.ingestion_agent import run_ingestion_agent
from app.services.agent.agents.resolution_agent import run_resolution_agent
from app.services.agent.agents.notification_agent import run_notification_agent
from app.services.agent.agents.closure_agent import run_closure_agent

logger = logging.getLogger(__name__)

COORDINATOR_SYSTEM_PROMPT = """You are a Coordinator Agent that manages a multi-agent ticket resolution system.

Your job is to:
1. Analyze the incoming ticket
2. Create an execution plan for the specialized agents
3. After all agents complete, compile a final summary

Specialized agents available:
- IngestionAgent: Keeps knowledge base fresh
- ResolutionAgent: Finds best matching resolution
- NotificationAgent: Sends email to assignee
- ClosureAgent: Closes or escalates ticket

Always run all agents in order: ingestion → resolution → notification → closure

Respond with JSON only:
{
  "plan": ["ingestion", "resolution", "notification", "closure"],
  "priority": "high" | "normal",
  "notes": "any special instructions"
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


# ── Coordinator nodes ─────────────────────────────────────────────────────────

def plan_node(state: TicketState) -> TicketState:
    """Coordinator LLM creates execution plan."""
    print(f"\n{'='*60}")
    print(f"[Coordinator] 🎯 Planning for ticket: {state['ticket_id']}")
    print(f"[Coordinator] Description: {state['description'][:100]}...")

    context = {
        "ticket_id": state["ticket_id"],
        "source_type": state["source_type"],
        "description": state["description"][:300],
        "has_assignee": bool(state.get("assignee_email")),
    }

    llm = _get_llm(state["tenant_id"])
    response = llm.invoke([
        SystemMessage(content=COORDINATOR_SYSTEM_PROMPT),
        HumanMessage(content=f"New ticket:\n{json.dumps(context, indent=2)}\n\nCreate execution plan."),
    ])

    raw = response.content.strip().strip("```json").strip("```").strip()
    try:
        plan = json.loads(raw)
    except Exception:
        plan = {
            "plan": ["ingestion", "resolution", "notification", "closure"],
            "priority": "normal",
            "notes": "Default plan",
        }

    print(f"[Coordinator] Plan: {plan['plan']} | Priority: {plan['priority']}")
    return {**state, "_plan": plan}


def run_agents_node(state: TicketState) -> TicketState:
    """Run each specialized agent in sequence."""
    plan = state.get("_plan", {})
    agents_to_run = plan.get("plan", ["ingestion", "resolution", "notification", "closure"])
    errors = []

    agent_map = {
        "ingestion":    run_ingestion_agent,
        "resolution":   run_resolution_agent,
        "notification": run_notification_agent,
        "closure":      run_closure_agent,
    }

    current_state = state

    for agent_name in agents_to_run:
        agent_fn = agent_map.get(agent_name)
        if not agent_fn:
            continue

        try:
            print(f"\n[Coordinator] ▶ Running {agent_name.upper()} agent...")
            current_state = agent_fn(current_state)
            print(f"[Coordinator] ✅ {agent_name.upper()} agent completed")
        except Exception as exc:
            error_msg = f"{agent_name} agent failed: {str(exc)}"
            logger.error("[Coordinator] %s", error_msg)
            errors.append(error_msg)
            print(f"[Coordinator] ❌ {agent_name.upper()} agent failed: {exc}")
            # Continue with next agent even if one fails

    return {**current_state, "errors": errors}


def summarize_node(state: TicketState) -> TicketState:
    """Coordinator compiles final summary."""
    print(f"\n[Coordinator] 📋 Compiling final summary...")

    summary_parts = [
        f"Ticket {state['ticket_id']} processed.",
        f"Ingestion: {state.get('ingestion_status', 'not run')}.",
        f"Resolution: {state.get('resolution_status', 'not run')} "
        f"(confidence={state.get('best_confidence', 0):.4f}).",
        f"Notification: {state.get('notification_status', 'not run')} "
        f"via {state.get('notification_channel', 'none')}.",
        f"Closure: {state.get('closure_decision', 'not run')}.",
    ]

    if state.get("errors"):
        summary_parts.append(f"Errors: {'; '.join(state['errors'])}")

    summary = " | ".join(summary_parts)

    print(f"[Coordinator] Summary: {summary}")
    print(f"{'='*60}\n")

    return {
        **state,
        "final_summary": summary,
        "done": True,
    }


# ── Build coordinator graph ───────────────────────────────────────────────────

def build_coordinator():
    graph = StateGraph(TicketState)
    graph.add_node("plan",       plan_node)
    graph.add_node("run_agents", run_agents_node)
    graph.add_node("summarize",  summarize_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan",       "run_agents")
    graph.add_edge("run_agents", "summarize")
    graph.add_edge("summarize",  END)

    return graph.compile()


# ── Public API ────────────────────────────────────────────────────────────────

def run_multi_agent_system(
    tenant_id: str,
    ticket_id: str,
    source_type: str,
    description: str,
    assignee_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Entry point for the full multi-agent system.
    Called by scheduler and API endpoint.
    """
    print(f"\n{'#'*60}")
    print(f"# MULTI-AGENT SYSTEM STARTING")
    print(f"# Ticket: {ticket_id} | Tenant: {tenant_id}")
    print(f"{'#'*60}")

    state = initial_state(
        tenant_id=tenant_id,
        ticket_id=ticket_id,
        source_type=source_type,
        description=description,
        assignee_email=assignee_email,
    )

    coordinator = build_coordinator()
    final_state = coordinator.invoke(state)

    return {
        "ticket_id":            ticket_id,
        "ingestion_status":     final_state.get("ingestion_status"),
        "resolution_status":    final_state.get("resolution_status"),
        "best_confidence":      final_state.get("best_confidence", 0),
        "best_ticket_id":       final_state.get("best_ticket_id"),
        "notification_status":  final_state.get("notification_status"),
        "notification_channel": final_state.get("notification_channel"),
        "closure_decision":     final_state.get("closure_decision"),
        "closure_reason":       final_state.get("closure_reason"),
        "steps_completed":      final_state.get("steps_completed", []),
        "errors":               final_state.get("errors", []),
        "final_summary":        final_state.get("final_summary"),
    }