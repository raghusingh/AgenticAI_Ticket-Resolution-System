"""
services/agent/ticket_agent.py

LangGraph stateful agent that autonomously processes new tickets.

Graph nodes:
  reason   → LLM decides which tool to call next
  act      → executes the chosen tool
  observe  → LLM evaluates result, decides if done or continues
  done     → terminal success node
  escalate → terminal escalation node

State:
  - ticket context (id, description, source, assignee)
  - action history (what was done so far)
  - rag results (matches found)
  - final decision (closed / escalated / notified)
"""

import json
import logging
import os
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain.schema import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from app.services.agent.agent_tools import (
    AGENT_TOOLS,
    ask_clarification,
    close_jira_ticket,
    escalate_ticket,
    search_rag,
    send_resolution_email,
)

logger = logging.getLogger(__name__)

TOOL_MAP = {t.name: t for t in AGENT_TOOLS}

CONFIDENCE_THRESHOLD = float(os.getenv("AUTO_CLOSE_CONFIDENCE_THRESHOLD", "0.85"))
MAX_ITERATIONS = 6  # prevent infinite loops


# ── Agent State ───────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    # Ticket context
    tenant_id:      str
    ticket_id:      str
    source_type:    str
    description:    str
    assignee_email: Optional[str]

    # Agent working memory
    iterations:     int
    action_history: List[Dict[str, Any]]   # list of {tool, input, result}
    rag_tickets:    List[Dict[str, Any]]   # matches from search_rag
    best_confidence: float

    # Final outcome
    decision:       str   # 'closed' | 'escalated' | 'notified' | 'clarification_needed'
    done:           bool
    summary:        str


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an intelligent ticket resolution agent.

Your job is to process a new support ticket by deciding which actions to take.

You have these tools available:
- search_rag: Search the knowledge base for similar resolved tickets
- send_resolution_email: Send resolution suggestions to the assignee
- close_jira_ticket: Close a ticket in Jira (only when confidence >= {threshold})
- escalate_ticket: Flag ticket for human review (when confidence < {threshold} or no match)
- ask_clarification: Log a clarifying question (when description is too vague)

Decision rules:
1. ALWAYS start with search_rag to find matching resolutions
2. If description is under 20 words or very vague → use ask_clarification first
3. If search_rag returns confidence >= {threshold} → send_resolution_email then close_jira_ticket
4. If search_rag returns confidence < {threshold} → send_resolution_email then escalate_ticket
5. If no matches found → escalate_ticket immediately
6. Never close a ticket without first sending an email
7. Stop after reaching a terminal action (close or escalate)

Always respond with a JSON object:
{{
  "thought": "your reasoning here",
  "tool": "tool_name",
  "tool_input": {{...tool input dict...}}
}}
""".format(threshold=CONFIDENCE_THRESHOLD)


# ── Node: reason ──────────────────────────────────────────────────────────────

def reason_node(state: AgentState) -> AgentState:
    """LLM decides which tool to call next based on current state."""

    print(f"\n[Agent:reason] Iteration {state['iterations'] + 1}/{MAX_ITERATIONS}")
    print(f"[Agent:reason] Actions so far: {[a['tool'] for a in state['action_history']]}")

    # Build context message
    context = {
        "ticket_id":      state["ticket_id"],
        "tenant_id":      state["tenant_id"],
        "source_type":    state["source_type"],
        "description":    state["description"],
        "assignee_email": state["assignee_email"],
        "best_confidence": state["best_confidence"],
        "actions_taken":  [
            {"tool": a["tool"], "result_status": json.loads(a["result"]).get("status")}
            for a in state["action_history"]
        ],
        "rag_ticket_count": len(state["rag_tickets"]),
    }

    llm = _get_llm(state["tenant_id"])

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Current state:\n{json.dumps(context, indent=2)}\n\nWhat should I do next?"),
    ]

    response = llm.invoke(messages)
    raw = response.content.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        decision = json.loads(raw)
    except Exception:
        # Fallback: escalate if LLM response is unparseable
        print(f"[Agent:reason] ⚠️  Could not parse LLM response — escalating")
        decision = {
            "thought": "Could not parse reasoning — escalating for safety.",
            "tool": "escalate_ticket",
            "tool_input": {
                "tenant_id":   state["tenant_id"],
                "ticket_id":   state["ticket_id"],
                "source_type": state["source_type"],
                "reason":      "Agent reasoning failed — requires human review.",
            },
        }

    print(f"[Agent:reason] 💭 Thought: {decision.get('thought', '')[:100]}")
    print(f"[Agent:reason] 🔧 Tool chosen: {decision.get('tool')}")

    return {
        **state,
        "_next_tool":       decision.get("tool"),
        "_next_tool_input": decision.get("tool_input", {}),
        "iterations":       state["iterations"] + 1,
    }


# ── Node: act ─────────────────────────────────────────────────────────────────

def act_node(state: AgentState) -> AgentState:
    """Execute the tool chosen by the reason node."""

    tool_name  = state.get("_next_tool", "escalate_ticket")
    tool_input = state.get("_next_tool_input", {})

    # Always inject tenant/ticket context into tool input
    tool_input.setdefault("tenant_id",   state["tenant_id"])
    tool_input.setdefault("ticket_id",   state["ticket_id"])
    tool_input.setdefault("source_type", state["source_type"])
    tool_input.setdefault("description", state["description"])
    tool_input.setdefault("assignee_email", state["assignee_email"])

    print(f"[Agent:act] ⚡ Executing tool: {tool_name}")

    tool_fn = TOOL_MAP.get(tool_name)
    if not tool_fn:
        result = json.dumps({"status": "error", "message": f"Unknown tool: {tool_name}"})
    else:
        try:
            result = tool_fn.invoke(json.dumps(tool_input))
        except Exception as exc:
            result = json.dumps({"status": "error", "message": str(exc)})

    print(f"[Agent:act] Result: {result[:120]}")

    # Update RAG tickets if this was a search
    rag_tickets    = state["rag_tickets"]
    best_confidence = state["best_confidence"]

    if tool_name == "search_rag":
        try:
            parsed = json.loads(result)
            rag_tickets     = parsed.get("tickets", [])
            best_confidence = max(
                (float(t.get("confidence_score", 0)) for t in rag_tickets),
                default=0.0,
            )
            print(f"[Agent:act] 📊 Best confidence: {best_confidence:.4f}")
        except Exception:
            pass

    # Attach tickets to email tool input for next iteration
    if tool_name == "send_resolution_email" and rag_tickets:
        pass  # already handled in tool itself via prefetched_tickets

    history = state["action_history"] + [{
        "tool":   tool_name,
        "input":  tool_input,
        "result": result,
    }]

    return {
        **state,
        "action_history":  history,
        "rag_tickets":     rag_tickets,
        "best_confidence": best_confidence,
    }


# ── Node: observe ─────────────────────────────────────────────────────────────

def observe_node(state: AgentState) -> AgentState:
    """
    Check if the agent has reached a terminal state.
    Terminal = close_jira_ticket or escalate_ticket was the last action.
    """
    if not state["action_history"]:
        return {**state, "done": False}

    last_tool   = state["action_history"][-1]["tool"]
    last_result = json.loads(state["action_history"][-1]["result"])
    last_status = last_result.get("status", "")

    terminal_tools = {"close_jira_ticket", "escalate_ticket", "ask_clarification"}
    over_limit     = state["iterations"] >= MAX_ITERATIONS

    if last_tool in terminal_tools or over_limit:
        # Map last tool → decision label
        decision_map = {
            "close_jira_ticket": "closed",
            "escalate_ticket":   "escalated",
            "ask_clarification": "clarification_needed",
        }
        decision = decision_map.get(last_tool, "notified")

        summary = (
            f"Ticket {state['ticket_id']} → {decision}. "
            f"Steps: {[a['tool'] for a in state['action_history']]}. "
            f"Best confidence: {state['best_confidence']:.4f}."
        )
        print(f"[Agent:observe] ✅ Done — {summary}")

        return {**state, "done": True, "decision": decision, "summary": summary}

    print(f"[Agent:observe] 🔄 Continuing — last tool={last_tool}, status={last_status}")
    return {**state, "done": False}


# ── Routing ───────────────────────────────────────────────────────────────────

def should_continue(state: AgentState) -> str:
    return "done" if state.get("done") else "reason"


# ── LLM factory ──────────────────────────────────────────────────────────────

def _get_llm(tenant_id: str):
    """
    Load LLM from tenant config — supports OpenAI and Gemini.
    Reads llm_provider from models section to decide which to use.
    """
    import json
    from pathlib import Path

    config_path = (
        Path(__file__).resolve().parents[3]
        / "config_store"
        / f"{tenant_id}_rag_config.json"
    )

    # Defaults
    provider   = "openai"
    model_name = "gpt-4o-mini"
    api_key    = os.getenv("OPENAI_API_KEY", "")

    if config_path.exists():
        with open(config_path) as f:
            raw = json.load(f)

        models  = raw.get("models", {})
        secrets = raw.get("secrets", {})

        provider   = (models.get("llm_provider") or "openai").lower().strip()
        model_name = models.get("llm_model_name") or model_name
        api_key    = secrets.get("llm_api_key") or ""

    print(f"[TicketAgent] LLM provider={provider} model={model_name}")

    if provider in ("openai",):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            temperature=0.1,
        )

    elif provider in ("google", "gemini"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=0.1,
            convert_system_message_to_human=True,  # Gemini requires this
        )

    else:
        raise ValueError(
            f"Unsupported LLM provider '{provider}' in tenant config. "
            f"Supported: 'openai', 'gemini'."
        )


# ── Build graph ───────────────────────────────────────────────────────────────

def build_agent_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("reason",  reason_node)
    graph.add_node("act",     act_node)
    graph.add_node("observe", observe_node)

    graph.set_entry_point("reason")
    graph.add_edge("reason", "act")
    graph.add_edge("act",    "observe")
    graph.add_conditional_edges(
        "observe",
        should_continue,
        {"reason": "reason", "done": END},
    )

    return graph.compile()


# ── Public API ────────────────────────────────────────────────────────────────

def run_ticket_agent(
    tenant_id:      str,
    ticket_id:      str,
    source_type:    str,
    description:    str,
    assignee_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the LangGraph agent for a single ticket.
    Returns the final state with decision, summary, and action history.
    """
    print(f"\n{'='*60}")
    print(f"[TicketAgent] 🤖 Starting agent for ticket: {ticket_id}")
    print(f"[TicketAgent] Tenant={tenant_id} Source={source_type}")
    print(f"{'='*60}")

    initial_state: AgentState = {
        "tenant_id":       tenant_id,
        "ticket_id":       ticket_id,
        "source_type":     source_type,
        "description":     description,
        "assignee_email":  assignee_email,
        "iterations":      0,
        "action_history":  [],
        "rag_tickets":     [],
        "best_confidence": 0.0,
        "decision":        "pending",
        "done":            False,
        "summary":         "",
        "_next_tool":      None,
        "_next_tool_input": {},
    }

    graph  = build_agent_graph()
    result = graph.invoke(initial_state)

    print(f"[TicketAgent] 🏁 Final decision: {result.get('decision')}")
    print(f"[TicketAgent] 📋 Summary: {result.get('summary')}")

    return {
        "ticket_id":       ticket_id,
        "decision":        result.get("decision", "unknown"),
        "summary":         result.get("summary", ""),
        "best_confidence": result.get("best_confidence", 0.0),
        "steps_taken":     len(result.get("action_history", [])),
        "action_history":  [
            {"tool": a["tool"], "status": json.loads(a["result"]).get("status")}
            for a in result.get("action_history", [])
        ],
    }
