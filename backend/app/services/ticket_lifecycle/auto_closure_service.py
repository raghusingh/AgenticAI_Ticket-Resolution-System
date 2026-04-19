"""
services/ticket_lifecycle/auto_closure_service.py

Decides whether a new ticket should be automatically closed
based on the confidence score of the best RAG match.

Decision logic
--------------
confidence >= threshold  →  auto_closed = True
confidence <  threshold  →  auto_closed = False  (human review needed)

The "closure" here means:
  • We record the decision in ticket_events.
  • For Jira source: the caller (webhook / scheduler) must call the Jira
    REST API with the returned resolution; we return what to use.
  • For SharePoint-local: same pattern — we return the resolution text.

We intentionally do NOT call the source API directly from this service
so that this layer stays testable and decoupled.
"""

import logging
from typing import Optional

from app.repositories.ai_config_repository import AIConfigRepository
from app.repositories.ticket_lifecycle_repository import TicketLifecycleRepository
from app.schemas.ticket_lifecycle import AutoCloseRequest, AutoCloseResult
from app.services.rag_service import RAGService

logger = logging.getLogger(__name__)

DEFAULT_CONFIDENCE_THRESHOLD = 0.85


def _build_tenant_config(raw_config: dict) -> dict:
    """Shared normaliser (mirrors chat.py logic)."""
    if "models" in raw_config:
        models = raw_config.get("models", {})
        secrets = raw_config.get("secrets", {})
        return {
            "tenant_id": raw_config.get("tenant_id"),
            "llm": {
                "provider": (models.get("llm_provider") or "").lower(),
                "model": models.get("llm_model_name"),
                "api_key": secrets.get("llm_api_key"),
                "temperature": models.get("temperature", 0.2),
                "max_tokens": models.get("max_tokens", 1000),
            },
            "embedding": {
                "provider": (models.get("embedding_provider") or "").lower(),
                "model": models.get("embedding_model_name"),
                "api_key": secrets.get("embedding_api_key"),
            },
            "vector_store": {"provider": "faiss", "index_path": "faiss_store/index"},
        }
    llm = raw_config.get("llm", {})
    embedding = raw_config.get("embedding", {})
    vs = raw_config.get("vector_store", {})
    return {
        "tenant_id": raw_config.get("tenant_id"),
        "llm": {
            "provider": (llm.get("provider") or "").lower(),
            "model": llm.get("model"),
            "api_key": llm.get("api_key"),
            "temperature": llm.get("temperature", 0.2),
            "max_tokens": llm.get("max_tokens", 1000),
        },
        "embedding": {
            "provider": (embedding.get("provider") or "").lower(),
            "model": embedding.get("model"),
            "api_key": embedding.get("api_key"),
        },
        "vector_store": {
            "provider": vs.get("provider", "faiss"),
            "index_path": vs.get("index_path", "faiss_store/index"),
        },
    }


class AutoClosureService:
    def __init__(self):
        self.config_repo = AIConfigRepository()
        self.lifecycle_repo = TicketLifecycleRepository()

    def evaluate(self, request: AutoCloseRequest) -> AutoCloseResult:
        """
        Core method:
          1. Guard against duplicate processing.
          2. Query RAG for best match.
          3. Apply threshold decision.
          4. Persist event.
          5. Return result (caller decides what to do with Jira/SP API).
        """
        # Guard: already processed?
        if self.lifecycle_repo.is_already_closed(request.tenant_id, request.ticket_id):
            logger.info("Ticket %s already auto-closed; skipping.", request.ticket_id)
            return AutoCloseResult(
                ticket_id=request.ticket_id,
                auto_closed=True,
                confidence_score=0.0,
                reason="Already processed — duplicate request ignored.",
            )

        raw_config = self.config_repo.get_tenant_config(request.tenant_id)
        if not raw_config:
            return AutoCloseResult(
                ticket_id=request.ticket_id,
                auto_closed=False,
                confidence_score=0.0,
                reason=f"Tenant config not found for {request.tenant_id}.",
            )

        tenant_config = _build_tenant_config(raw_config)

        try:
            rag = RAGService(tenant_config)
            rag_result = rag.ask(request.description, top_k=5)
        except Exception as exc:
            logger.error("RAG query failed for ticket %s: %s", request.ticket_id, exc)
            return AutoCloseResult(
                ticket_id=request.ticket_id,
                auto_closed=False,
                confidence_score=0.0,
                reason=f"RAG query failed: {exc}",
            )

        tickets = rag_result.get("tickets", [])
        if not tickets:
            self.lifecycle_repo.record_event(
                tenant_id=request.tenant_id,
                ticket_id=request.ticket_id,
                source_type=request.source_type,
                event_type="skipped",
                reason="No RAG matches found.",
            )
            return AutoCloseResult(
                ticket_id=request.ticket_id,
                auto_closed=False,
                confidence_score=0.0,
                reason="No matching tickets found in knowledge base.",
            )

        best = tickets[0]
        confidence = float(best.get("confidence_score", 0.0))
        threshold = request.confidence_threshold or DEFAULT_CONFIDENCE_THRESHOLD

        should_close = confidence >= threshold

        event_type = "auto_closed" if should_close else "skipped"
        reason = (
            f"Confidence {confidence:.4f} ≥ threshold {threshold:.4f} → auto-closed."
            if should_close
            else f"Confidence {confidence:.4f} < threshold {threshold:.4f} → routed for human review."
        )

        self.lifecycle_repo.record_event(
            tenant_id=request.tenant_id,
            ticket_id=request.ticket_id,
            source_type=request.source_type,
            event_type=event_type,
            confidence=confidence,
            matched_ticket_id=best.get("ticket_id"),
            resolution=best.get("resolution"),
            reason=reason,
        )

        logger.info(
            "Auto-closure decision for %s: %s (confidence=%.4f)",
            request.ticket_id, event_type, confidence,
        )

        return AutoCloseResult(
            ticket_id=request.ticket_id,
            auto_closed=should_close,
            confidence_score=confidence,
            matched_ticket_id=best.get("ticket_id"),
            resolution=best.get("resolution"),
            root_cause=best.get("root_cause"),
            reason=reason,
        )
