import re
from typing import Any, Dict, List

from app.factories.provider_factory import ProviderFactory
from app.repositories.rag_admin_repository import RagAdminRepository
from app.services.ingestion_service import IngestionService


class RAGService:
    def __init__(self, tenant_config: dict):
        self.tenant_config = tenant_config or {}

        llm_config = self.tenant_config.get("llm", {})
        embedding_config = self.tenant_config.get("embedding", {})
        vector_store_config = self.tenant_config.get("vector_store", {})

        if not llm_config:
            raise ValueError("LLM config is missing")
        if not embedding_config:
            raise ValueError("Embedding config is missing")
        if not vector_store_config:
            raise ValueError("Vector store config is missing")

        if not llm_config.get("api_key"):
            raise ValueError("LLM API key missing in tenant_config['llm']['api_key']")
        if not embedding_config.get("api_key"):
            raise ValueError("Embedding API key missing in tenant_config['embedding']['api_key']")

        self.embedding_provider = ProviderFactory.create_embedding(embedding_config)
        self.vector_store = ProviderFactory.create_vector_store(
            vector_store_config,
            self.embedding_provider,
        )
        self.llm_provider = ProviderFactory.create_llm(llm_config)

    def ask(self, question: str, top_k: int = 5) -> dict:
        tenant_id = self.tenant_config.get("tenant_id")
        if not tenant_id:
            raise ValueError("tenant_id is missing in tenant_config")

        repo = RagAdminRepository()
        ingestion_service = IngestionService(repo)
        retrieval_result = ingestion_service.query(tenant_id, question)

        docs = retrieval_result.get("tickets", [])[:top_k]
        tickets = self._build_ticket_rows(docs)

        summary_prompt = self._build_summary_prompt(question, tickets)
        answer = self.llm_provider.generate(summary_prompt, context=tickets)

        return {
            "answer": answer,
            "tickets": tickets,
            "sources": docs,
            "llm_model": self.llm_provider.model_name(),
            "embedding_model": self.embedding_provider.model_name(),
            "vector_store": "faiss",
        }

    def _build_ticket_rows(self, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []

        for doc in docs:
            metadata = doc.get("metadata", {}) or {}
            text = metadata.get("text", "") or ""
            score = doc.get("score")

            source_type = metadata.get("source_type", "") or ""
            source_name = metadata.get("source_name", "") or ""

            ticket_id = self._extract_field(text, "Issue Key")
            issue_type = self._extract_field(text, "Type")
            summary = self._extract_field(text, "Summary")
            status = self._extract_field(text, "Status")
            priority = self._extract_field(text, "Priority")

            # Handle both Jira-style and SharePoint-local structured blocks
            detailed_description = self._extract_field(text, "Detailed Description")
            resolution_notes = self._extract_field(text, "Resolution Notes")
            root_cause = self._extract_field(text, "Root Cause")

            description = summary or detailed_description
            resolution = (
                resolution_notes
                or self._extract_field(text, "Resolution")
                or self._extract_block(text, "Description")   # ✅ Jira fallback
            )

            root_cause = self._extract_field(text, "Root Cause")

            # 🔥 Fallback: extract from resolution text
            if not root_cause:
                resolution_text = resolution or text
                match = re.search(r"root\s*cause[:\-]?\s*(.+)", resolution_text, re.IGNORECASE)
                if match:
                    root_cause = match.group(1).strip()
                    
            # Skip empty junk rows
            if not any([ticket_id, description, resolution, root_cause]):
                continue

            rows.append({
                "source": source_type or source_name or metadata.get("collection", "unknown"),
                "source_type": source_type or source_name or "unknown",
                "ticket_id": ticket_id or metadata.get("source_name", ""),
                "ticket_description": description or text[:120],
                "resolution": resolution or "",
                "root_cause": root_cause or "",
                "issue_type": issue_type or source_type or "",
                "status": status or "",
                "priority": priority or "",
                "confidence_score": self._normalize_score(score),
                "source_url": metadata.get("source_url"),
            })

        return rows

    def _extract_block(self, text: str, field_name: str) -> str:
        pattern = rf"(?ims){re.escape(field_name)}:\s*(.*?)(?:\n[A-Z][a-zA-Z ]+:|\Z)"
        match = re.search(pattern, text)
        return match.group(1).strip() if match else ""

    def _build_summary_prompt(self, question: str, tickets: List[Dict[str, Any]]) -> str:
        if not tickets:
            return f"""
You are a helpful assistant.
No matching tickets were found for this question.

User question:
{question}

Reply in 1-2 lines only.
""".strip()

        ticket_lines = []
        for t in tickets:
            ticket_lines.append(
                f"- {t.get('ticket_id')}: {t.get('ticket_description')} | "
                f"Resolution: {t.get('resolution')} | "
                f"Root Cause: {t.get('root_cause')} | "
                f"Type: {t.get('issue_type')} | Status: {t.get('status')} | "
                f"Confidence: {t.get('confidence_score')}"
            )

        ticket_block = "\n".join(ticket_lines)

        return f"""
You are a helpful assistant.
The user wants similar tickets.

Summarize the below results in 3-5 lines.
Do not invent details.
Mention the most relevant ticket ids.

User question:
{question}

Tickets:
{ticket_block}
""".strip()

    def _extract_field(self, text: str, field_name: str) -> str:
        pattern = rf"{re.escape(field_name)}:\s*(.+)"
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def _normalize_score(self, score: Any) -> float:
        if score is None:
            return 0.0

        try:
            score_val = float(score)
        except Exception:
            return 0.0

        confidence = 1.0 / (1.0 + max(score_val, 0.0))
        return round(confidence, 4)