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

        # ✅ Use raw results (sources) not pre-filtered tickets
        # so we can build rows ourselves with full control
        raw_docs = retrieval_result.get("results", [])[:top_k]
        all_tickets = self._build_ticket_rows(raw_docs)

        # ✅ LLM re-ranking — filter ALL irrelevant tickets
        # including open ones that don't match the query
        tickets = self._rerank_tickets(question, all_tickets)

        summary_prompt = self._build_summary_prompt(question, tickets)
        answer = self.llm_provider.generate(summary_prompt, context=tickets)

        return {
            "answer": answer,
            "tickets": tickets,
            "sources": raw_docs,
            "llm_model": self.llm_provider.model_name(),
            "embedding_model": self.embedding_provider.model_name(),
            "vector_store": "faiss",
        }

    def _rerank_tickets(self, question: str, tickets: list) -> list:
        """
        Use LLM to filter out tickets not relevant to the question.
        Only keeps tickets where the problem type genuinely matches.
        """
        if not tickets:
            return []

        import json as _json

        ticket_list = []
        for i, t in enumerate(tickets):
            ticket_list.append({
                "index": i,
                "ticket_id": t.get("ticket_id"),
                "description": (t.get("ticket_description") or "")[:150],
                "resolution": (t.get("resolution") or "")[:150],
                "status": t.get("status"),
            })

        prompt = (
            f'You are a strict ticket relevance filter.\n\n'
            f'User query: "{question}"\n\n'
            f'Evaluate each candidate ticket below.\n'
            f'Keep a ticket ONLY if its description directly relates to the SAME type of problem.\n'
            f'Apply this rule to BOTH open and closed tickets.\n\n'
            f'Examples of what to REJECT:\n'
            f'- User asks about "500 error" → reject "CPU high", "API failure", "Payment Gateway"\n'
            f'- User asks about "login issue" → reject "database timeout", "network outage"\n\n'
            f'Candidates:\n{_json.dumps(ticket_list, indent=2)}\n\n'
            f'Return JSON only:\n{{"relevant_indices": [list of integer indices]}}'
        )

        try:
            raw = self.llm_provider.generate(prompt, context=[])
            # Clean up response — strip markdown, whitespace
            raw = raw.strip()
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            # Find JSON object in response
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                raw = raw[start:end]

            result = _json.loads(raw)
            relevant_indices = result.get("relevant_indices", [])
            filtered = [tickets[i] for i in relevant_indices if isinstance(i, int) and i < len(tickets)]
            print(f"[RAGService] Re-ranking: {len(tickets)} → {len(filtered)} relevant")
            print(f"[RAGService] Kept indices: {relevant_indices}")
            # Only fall back if LLM completely failed (exception), not if it returned empty list
            return filtered
        except Exception as exc:
            print(f"[RAGService] Re-ranking failed: {exc} — returning all")
            return tickets

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
            comments_raw = self._extract_field(text, "Comments")

            description = summary or detailed_description

            # ── Resolution extraction priority ───────────────────────────────
            jira_status_words = {
                "done", "fixed", "won't fix", "duplicate",
                "cannot reproduce", "incomplete", ""
            }

            # 1. Try Resolution Notes first (SharePoint)
            resolution = resolution_notes or ""

            # 2. Try Resolution field — skip if it's just a Jira status word
            if not resolution:
                raw_res = self._extract_field(text, "Resolution")
                if raw_res and raw_res.lower() not in jira_status_words:
                    resolution = raw_res

            # 3. Try extracting Reason from Comments field
            if not resolution and comments_raw:
                # Strip "Comments:" label and "[Author]:" prefix
                cleaned = re.sub(r"^Comments:\s*", "", comments_raw.strip(), flags=re.IGNORECASE)
                cleaned = re.sub(r"^\[[^\]]+\]:\s*", "", cleaned.strip())
                # Extract "Reason: <text>" if present
                reason_match = re.search(r"Reason:\s*(.+)", cleaned, re.IGNORECASE)
                if reason_match:
                    resolution = reason_match.group(1).strip()
                elif cleaned and len(cleaned) > 10:
                    resolution = cleaned

            # 4. Final cleanup — strip any remaining Comments/author prefix
            if resolution:
                resolution = re.sub(r"^Comments:\s*", "", resolution.strip(), flags=re.IGNORECASE)
                resolution = re.sub(r"^\[[^\]]+\]:\s*", "", resolution.strip())
                reason_match = re.search(r"Reason:\s*(.+)", resolution, re.IGNORECASE)
                if reason_match:
                    resolution = reason_match.group(1).strip()

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

            # ✅ For open tickets — show in results but blank resolution + confidence
            open_statuses = {
                "to do", "open", "in progress", "in review",
                "reopened", "pending", "new", "assigned", "on hold"
            }
            is_open = status.lower() in open_statuses
            if is_open:
                resolution = ""
                root_cause = ""

            rows.append({
                "source": source_type or source_name or metadata.get("collection", "unknown"),
                "source_type": source_type or source_name or "unknown",
                "ticket_id": ticket_id or metadata.get("source_name", ""),
                "ticket_description": description or text[:120],
                "resolution": resolution if not is_open else "",
                "root_cause": root_cause if not is_open else "",
                "issue_type": issue_type or source_type or "",
                "status": status or "",
                "priority": priority or "",
                "confidence_score": self._normalize_score(score) if not is_open else None,
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