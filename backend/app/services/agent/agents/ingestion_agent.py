"""
services/agent/agents/ingestion_agent.py

Ingestion Agent — specialized agent that manages the knowledge base.

Responsibilities:
  - Check if KB needs refreshing based on last ingestion time
  - Re-ingest from Jira/SharePoint when needed
  - Report ingestion status back to coordinator

This agent has its OWN LLM reasoning loop — it decides
whether ingestion is needed based on context.
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from langchain.schema import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from app.services.agent.agents.agent_state import TicketState

logger = logging.getLogger(__name__)

INGESTION_SYSTEM_PROMPT = """You are an Ingestion Agent responsible for keeping the knowledge base fresh.

Your job is to decide whether the knowledge base needs to be re-ingested before searching.

Rules:
1. If the knowledge base was last updated more than 1 hour ago → re-ingest
2. If the knowledge base files don't exist → re-ingest
3. If the last ingestion failed → re-ingest
4. Otherwise → skip ingestion (it's fresh enough)

Respond with JSON only:
{
  "decision": "ingest" | "skip",
  "reason": "brief reason"
}
"""


def _get_llm(tenant_id: str):
    """Load LLM from tenant config."""
    import json
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


def _check_kb_freshness(tenant_id: str) -> dict:
    """Check when KB was last updated."""
    base = Path(__file__).resolve().parents[4]
    faiss_dir = base / "faiss_store"
    index_files = list(faiss_dir.glob(f"{tenant_id}_*.index")) if faiss_dir.exists() else []

    if not index_files:
        return {"exists": False, "age_minutes": None, "last_updated": None}

    latest = max(index_files, key=lambda f: f.stat().st_mtime)
    age_seconds = (datetime.now().timestamp() - latest.stat().st_mtime)
    age_minutes = age_seconds / 60

    return {
        "exists": True,
        "age_minutes": round(age_minutes, 1),
        "last_updated": datetime.fromtimestamp(latest.stat().st_mtime).isoformat(),
    }


def _run_ingestion(tenant_id: str) -> dict:
    """Actually run the ingestion pipeline."""
    try:
        from app.repositories.rag_admin_repository import RagAdminRepository
        from app.services.ingestion_service import IngestionService

        repo = RagAdminRepository()
        svc = IngestionService(repo)
        result = svc.run(tenant_id)
        return result
    except Exception as exc:
        logger.error("[IngestionAgent] Ingestion failed: %s", exc)
        return {"status": "failed", "message": str(exc)}


# ── Agent nodes ───────────────────────────────────────────────────────────────

def reason_node(state: TicketState) -> TicketState:
    """LLM decides whether to ingest."""
    print(f"[IngestionAgent] 🧠 Reasoning about KB freshness...")

    kb_info = _check_kb_freshness(state["tenant_id"])
    context = {
        "tenant_id": state["tenant_id"],
        "kb_exists": kb_info["exists"],
        "kb_age_minutes": kb_info["age_minutes"],
        "kb_last_updated": kb_info["last_updated"],
    }

    llm = _get_llm(state["tenant_id"])
    response = llm.invoke([
        SystemMessage(content=INGESTION_SYSTEM_PROMPT),
        HumanMessage(content=f"KB status:\n{json.dumps(context, indent=2)}\n\nShould I re-ingest?"),
    ])

    raw = response.content.strip().strip("```json").strip("```").strip()
    try:
        decision = json.loads(raw)
    except Exception:
        decision = {"decision": "skip", "reason": "Could not parse response"}

    print(f"[IngestionAgent] Decision: {decision['decision']} — {decision['reason']}")
    return {**state, "_ingest_decision": decision["decision"], "_ingest_reason": decision["reason"]}


def act_node(state: TicketState) -> TicketState:
    """Execute ingestion if decided."""
    decision = state.get("_ingest_decision", "skip")

    if decision == "ingest":
        print(f"[IngestionAgent] ⚡ Running ingestion for {state['tenant_id']}...")
        result = _run_ingestion(state["tenant_id"])
        status = "refreshed" if result.get("status") == "success" else "failed"
        message = result.get("message", "")
    else:
        print(f"[IngestionAgent] ⏭️  KB is fresh — skipping ingestion")
        status = "fresh"
        message = state.get("_ingest_reason", "KB is fresh")

    steps = state.get("steps_completed", []) + ["ingestion"]
    return {
        **state,
        "ingestion_status": status,
        "ingestion_message": message,
        "steps_completed": steps,
    }


# ── Build graph ───────────────────────────────────────────────────────────────

def build_ingestion_agent():
    graph = StateGraph(TicketState)
    graph.add_node("reason", reason_node)
    graph.add_node("act", act_node)
    graph.set_entry_point("reason")
    graph.add_edge("reason", "act")
    graph.add_edge("act", END)
    return graph.compile()


def run_ingestion_agent(state: TicketState) -> TicketState:
    """Entry point called by coordinator."""
    print(f"\n[IngestionAgent] 🚀 Starting for tenant={state['tenant_id']}")
    graph = build_ingestion_agent()
    result = graph.invoke(state)
    print(f"[IngestionAgent] ✅ Done — status={result['ingestion_status']}")
    return result