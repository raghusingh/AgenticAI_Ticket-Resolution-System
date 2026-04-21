"""
services/agent/agents/resolution_agent.py

Resolution Agent — specialized agent that finds the best resolution.

Responsibilities:
  - Search FAISS vector DB for similar resolved tickets
  - Rank and evaluate results
  - Pick the best match based on confidence + relevance
  - Report resolution + confidence back to coordinator

This agent has its OWN LLM reasoning loop.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from langchain.schema import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from app.services.agent.agents.agent_state import TicketState

logger = logging.getLogger(__name__)

RESOLUTION_SYSTEM_PROMPT = """You are a Resolution Agent specialized in finding the best resolution for support tickets.

You have access to a list of similar resolved tickets from the knowledge base.
Your job is to:
1. Evaluate which ticket is the BEST match for the new ticket
2. Assess if the confidence is high enough to auto-close (threshold: 0.85)
3. Extract the most relevant resolution text

Respond with JSON only:
{
  "best_ticket_id": "ticket id of best match or empty string",
  "best_resolution": "the resolution text to use",
  "confidence": 0.0,
  "quality": "high" | "medium" | "low" | "none",
  "reasoning": "brief explanation of your choice"
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


def _search_rag(tenant_id: str, description: str, top_k: int = 5) -> List[Dict]:
    """Search FAISS for similar tickets."""
    try:
        from app.repositories.rag_admin_repository import RagAdminRepository
        from app.services.ingestion_service import IngestionService

        repo = RagAdminRepository()
        svc = IngestionService(repo)
        result = svc.query(tenant_id, description, top_k=top_k)
        return result.get("tickets", [])
    except Exception as exc:
        logger.error("[ResolutionAgent] RAG search failed: %s", exc)
        return []


# ── Agent nodes ───────────────────────────────────────────────────────────────

def search_node(state: TicketState) -> TicketState:
    """Search FAISS for similar tickets."""
    print(f"[ResolutionAgent] 🔍 Searching knowledge base...")
    tickets = _search_rag(state["tenant_id"], state["description"])
    print(f"[ResolutionAgent] Found {len(tickets)} candidate(s)")
    for i, t in enumerate(tickets[:3], 1):
        print(f"  [{i}] {t.get('ticket_id')} | "
              f"conf={t.get('confidence_score', 0):.4f} | "
              f"status={t.get('status')} | "
              f"resolution={str(t.get('resolution', ''))[:50]}")
    return {**state, "_rag_tickets": tickets}


def evaluate_node(state: TicketState) -> TicketState:
    """LLM evaluates results and picks best match."""
    tickets = state.get("_rag_tickets", [])

    if not tickets:
        print(f"[ResolutionAgent] ⚠️  No tickets found — skipping evaluation")
        steps = state.get("steps_completed", []) + ["resolution"]
        return {
            **state,
            "rag_tickets": [],
            "best_confidence": 0.0,
            "best_resolution": "",
            "best_ticket_id": "",
            "resolution_status": "not_found",
            "steps_completed": steps,
        }

    print(f"[ResolutionAgent] 🧠 Evaluating {len(tickets)} candidate(s)...")

    # Build context for LLM
    ticket_summary = []
    for t in tickets:
        ticket_summary.append({
            "ticket_id": t.get("ticket_id"),
            "description": t.get("ticket_description", "")[:200],
            "resolution": t.get("resolution", "")[:200],
            "status": t.get("status"),
            "confidence_score": t.get("confidence_score"),
        })

    context = {
        "new_ticket": {
            "ticket_id": state["ticket_id"],
            "description": state["description"],
        },
        "candidates": ticket_summary,
        "confidence_threshold": 0.85,
    }

    llm = _get_llm(state["tenant_id"])
    response = llm.invoke([
        SystemMessage(content=RESOLUTION_SYSTEM_PROMPT),
        HumanMessage(content=f"Evaluate these candidates:\n{json.dumps(context, indent=2)}"),
    ])

    raw = response.content.strip().strip("```json").strip("```").strip()
    try:
        evaluation = json.loads(raw)
    except Exception:
        evaluation = {
            "best_ticket_id": tickets[0].get("ticket_id", ""),
            "best_resolution": tickets[0].get("resolution", ""),
            "confidence": float(tickets[0].get("confidence_score", 0)),
            "quality": "medium",
            "reasoning": "Fallback to top result",
        }

    print(f"[ResolutionAgent] Best match: {evaluation.get('best_ticket_id')} | "
          f"quality={evaluation.get('quality')} | conf={evaluation.get('confidence'):.4f}")
    print(f"[ResolutionAgent] Reasoning: {evaluation.get('reasoning')}")

    steps = state.get("steps_completed", []) + ["resolution"]
    return {
        **state,
        "rag_tickets": tickets,
        "best_confidence": float(evaluation.get("confidence", 0)),
        "best_resolution": evaluation.get("best_resolution", ""),
        "best_ticket_id": evaluation.get("best_ticket_id", ""),
        "resolution_status": "found" if tickets else "not_found",
        "steps_completed": steps,
    }


# ── Build graph ───────────────────────────────────────────────────────────────

def build_resolution_agent():
    graph = StateGraph(TicketState)
    graph.add_node("search", search_node)
    graph.add_node("evaluate", evaluate_node)
    graph.set_entry_point("search")
    graph.add_edge("search", "evaluate")
    graph.add_edge("evaluate", END)
    return graph.compile()


def run_resolution_agent(state: TicketState) -> TicketState:
    """Entry point called by coordinator."""
    print(f"\n[ResolutionAgent] 🚀 Starting for ticket={state['ticket_id']}")
    graph = build_resolution_agent()
    result = graph.invoke(state)
    print(f"[ResolutionAgent] ✅ Done — status={result['resolution_status']} "
          f"confidence={result['best_confidence']:.4f}")
    return result