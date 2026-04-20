import os
import re
import time
import faiss
import numpy as np
import hashlib
import logging
from typing import List, Dict, Any
from datetime import datetime

from app.providers.llm.gemini_provider import GeminiProvider
from app.services.ingestors.jira_ingestor import JiraIngestor
from app.services.ingestors.sharepoint_ingestor import SharePointIngestor
from app.services.ingestors.sharepoint_local_ingestor import SharePointLocalIngestor

logger = logging.getLogger(__name__)


class EmbeddingClient:
    def embed_documents(self, texts, config, api_key):
        provider = config.get("provider", "gemini").lower()
        model = config["model"]

        if provider in ["google", "gemini"]:
            provider = "gemini"

        cleaned_texts = [str(t or "").strip() for t in texts if str(t or "").strip()]
        if not cleaned_texts:
            return []
        
        if provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)

            response = client.embeddings.create(
                model=model,
                input=cleaned_texts
            )
            return [item.embedding for item in response.data]

        elif provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=api_key)

            embeddings = []
            for text in cleaned_texts:
                response = genai.embed_content(
                    model=model,
                    content=text
                )
                embeddings.append(response["embedding"])

            return embeddings

        else:
            raise ValueError(f"Unsupported embedding provider: {provider}")


class FAISSVectorDB:
    def __init__(self, base_path="faiss_store"):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.base_path = os.path.join(project_root, base_path)
        os.makedirs(self.base_path, exist_ok=True)

        self.index_cache = {}
        self.metadata_cache = {}

        print("FAISS PROJECT ROOT:", project_root)
        print("FAISS BASE PATH:", self.base_path)

    def _get_index_path(self, collection_name):
        return os.path.join(self.base_path, f"{collection_name}.index")

    def _get_meta_path(self, collection_name):
        return os.path.join(self.base_path, f"{collection_name}_meta.npy")

    def _load_or_create_index(self, collection_name, dim):
        if collection_name in self.index_cache:
            return self.index_cache[collection_name]

        index_path = self._get_index_path(collection_name)

        if os.path.exists(index_path):
            index = faiss.read_index(index_path)
        else:
            index = faiss.IndexFlatL2(dim)

        self.index_cache[collection_name] = index
        return index

    def _load_metadata(self, collection_name):
        if collection_name in self.metadata_cache:
            return self.metadata_cache[collection_name]

        meta_path = self._get_meta_path(collection_name)
        if os.path.exists(meta_path):
            metadata = list(np.load(meta_path, allow_pickle=True))
        else:
            metadata = []

        self.metadata_cache[collection_name] = metadata
        return metadata

    def upsert(self, collection_name: str, vectors: List[Dict]):
        if not vectors:
            return

        dim = len(vectors[0]["values"])
        existing_meta = self._load_metadata(collection_name)

        # ── Deduplicate: build a map of ticket_id → index in existing_meta ──
        def _extract_ticket_id(meta: dict) -> str:
            text = str(meta.get("text") or "")
            match = re.search(r"Issue Key:\s*(.+)", text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
            # Fallback: use source_name or empty string
            return str(meta.get("source_name") or "")

        # Build index map of existing ticket_ids → position
        existing_id_map = {}
        for i, meta in enumerate(existing_meta):
            tid = _extract_ticket_id(meta)
            if tid:
                existing_id_map[tid] = i

        # Separate new vectors into: replacements and additions
        replaced_indices = set()
        replacement_map = {}  # existing index → new metadata

        additions_values = []
        additions_meta = []

        for v in vectors:
            tid = _extract_ticket_id(v["metadata"])
            if tid and tid in existing_id_map:
                # Replace existing entry
                idx = existing_id_map[tid]
                replaced_indices.add(idx)
                replacement_map[idx] = (v["values"], v["metadata"])
                print(f"[FAISSVectorDB] ♻️  Updating existing vector for ticket: {tid}")
            else:
                # New entry
                additions_values.append(v["values"])
                additions_meta.append(v["metadata"])

        # Rebuild metadata and collect surviving + updated vectors
        surviving_values = []
        surviving_meta = []

        # We need to reload the index to rebuild it without deleted entries
        index_path = self._get_index_path(collection_name)
        if os.path.exists(index_path) and existing_meta:
            old_index = faiss.read_index(index_path)
            for i, meta in enumerate(existing_meta):
                if i in replacement_map:
                    # Use updated values
                    surviving_values.append(replacement_map[i][0])
                    surviving_meta.append(replacement_map[i][1])
                else:
                    # Keep existing — reconstruct vector from index
                    vec = np.zeros((1, dim), dtype="float32")
                    old_index.reconstruct(i, vec[0])
                    surviving_values.append(vec[0].tolist())
                    surviving_meta.append(meta)
        else:
            surviving_values = []
            surviving_meta = []

        # Add new entries
        all_values = surviving_values + additions_values
        all_meta = surviving_meta + additions_meta

        if not all_values:
            return

        # Rebuild FAISS index from scratch with deduped vectors
        new_index = faiss.IndexFlatL2(dim)
        embeddings = np.array(all_values, dtype="float32")
        new_index.add(embeddings)

        # Invalidate cache and save
        self.index_cache[collection_name] = new_index
        self.metadata_cache[collection_name] = all_meta

        meta_path = self._get_meta_path(collection_name)
        os.makedirs(os.path.dirname(meta_path), exist_ok=True)
        np.save(meta_path, np.array(all_meta, dtype=object))
        faiss.write_index(new_index, self._get_index_path(collection_name))
        print(f"[FAISSVectorDB] ✅ Upserted {len(vectors)} vector(s) — "
              f"total in index: {new_index.ntotal}")

    def search(self, collection_name: str, query_vector: List[float], top_k=5):
        index_path = self._get_index_path(collection_name)
        meta_path = self._get_meta_path(collection_name)

        if not os.path.exists(index_path) or not os.path.exists(meta_path):
            return []

        if collection_name in self.index_cache:
            index = self.index_cache[collection_name]
        else:
            index = faiss.read_index(index_path)
            self.index_cache[collection_name] = index

        metadata = self._load_metadata(collection_name)

        if not metadata:
            return []

        query = np.array([query_vector], dtype="float32")
        distances, indices = index.search(query, top_k)

        results = []
        for i, idx in enumerate(indices[0]):
            if idx < 0 or idx >= len(metadata):
                continue

            results.append({
                "score": float(distances[0][i]),
                "metadata": metadata[idx]
            })

        return results


class IngestionService:
    def __init__(self, repo):
        self.repo = repo
        self.embedding_client = EmbeddingClient()
        self.vector_db = FAISSVectorDB()
        self.jira_ingestor = JiraIngestor()
        self.sharepoint_ingestor = SharePointIngestor()
        self.sharepoint_local_ingestor = SharePointLocalIngestor()

    def run(self, tenant_id: str) -> Dict[str, Any]:
        config = self.repo.get_setup(tenant_id)

        if not config:
            return {
                "status": "failed",
                "tenant_id": tenant_id,
                "message": "Tenant config not found",
                "total_docs": 0,
                "total_chunks": 0,
                "timestamp": datetime.utcnow().isoformat()
            }

        data_sources = config.get("data_sources", [])
        if not data_sources:
            return {
                "status": "failed",
                "tenant_id": tenant_id,
                "message": "No data_sources found in tenant config",
                "total_docs": 0,
                "total_chunks": 0,
                "timestamp": datetime.utcnow().isoformat()
            }

        total_docs = 0
        total_chunks = 0

        for source in data_sources:
            try:
                if not source.get("is_enabled", True):
                    continue

                print("DEBUG SOURCE:", source)
                print("DEBUG source_type:", source.get("source_type"))
                print("DEBUG is_enabled:", source.get("is_enabled", True))

                docs = self.extract(source, config)
                print("DEBUG extracted docs count:", len(docs))

                total_docs += len(docs)

                if not docs:
                    continue

                chunks = self.chunk(docs, source)
                if not chunks:
                    continue

                embeddings = self.embed(chunks, config)
                if not embeddings:
                    continue

                self.store(embeddings, source, tenant_id)
                total_chunks += len(embeddings)

            except Exception:
                logger.exception(f"Ingestion failed for source: {source.get('source_name')}")
                raise

        return {
            "status": "success" if total_chunks > 0 else "failed",
            "tenant_id": tenant_id,
            "total_docs": total_docs,
            "total_chunks": total_chunks,
            "message": "No source documents were fetched." if total_chunks == 0 else "Ingestion completed successfully.",
            "timestamp": datetime.utcnow().isoformat()
        }

    def query(self, tenant_id: str, question: str, generate_answer: bool = False, top_k: int = 5):
        config = self.repo.get_setup(tenant_id)
        if not config:
            raise ValueError(f"Tenant config not found for tenant_id={tenant_id}")

        model_config = config.get("models", {})
        embedding_model = model_config.get("embedding_model_name")
        if not embedding_model:
            raise ValueError("Embedding model is missing in config: models.embedding_model_name")

        secrets = config.get("secrets", {})
        embedding_api_key = secrets.get("embedding_api_key")
        if not embedding_api_key:
            raise ValueError("Embedding API key is missing in config: secrets.embedding_api_key")

        t0 = time.time()
        query_vectors = self.embedding_client.embed_documents(
            [question],
            {
                "model": embedding_model,
                "provider": model_config.get("embedding_provider", "gemini")
            },
            embedding_api_key
        )
        print("DEBUG embed question time:", time.time() - t0)

        if not query_vectors:
            raise ValueError("Failed to create query embedding")

        query_vector = query_vectors[0]

        t1 = time.time()
        results = []
        searched_collections = set()

        for source in config.get("data_sources", []):
            if not source.get("is_enabled", True):
                continue

            collection = f"{tenant_id}_{source.get('collection_name', 'default')}"
            if collection in searched_collections:
                continue

            searched_collections.add(collection)
            res = self.vector_db.search(collection, query_vector, top_k=top_k)
            results.extend(res)

        print("DEBUG vector search time:", time.time() - t1)

        results.sort(key=lambda x: x["score"])

        deduped = []
        seen_texts = set()

        for item in results:
            text = (item.get("metadata", {}) or {}).get("text", "").strip()
            if text and text not in seen_texts:
                seen_texts.add(text)
                deduped.append(item)

        top_results = deduped[:top_k]

        def compact_context(text: str) -> str:
            lines = []
            for field in [
                "Issue Key",
                "Type",
                "Summary",
                "Status",
                "Priority",
                "Detailed Description",
                "Resolution",
                "Resolution Date",
            ]:
                pattern = rf"(?im)^{re.escape(field)}:\s*(.*)$"
                match = re.search(pattern, text)
                if match:
                    lines.append(f"{field}: {match.group(1).strip()}")
            return "\n".join(lines)

        context = "\n\n".join([
            compact_context(r.get("metadata", {}).get("text", ""))
            for r in top_results
            if r.get("metadata", {}).get("text")
        ])

        answer = ""

        if generate_answer and top_results:
            llm_api_key = secrets.get("llm_api_key")
            if not llm_api_key:
                raise ValueError("LLM API key is missing in config: secrets.llm_api_key")

            llm_provider = model_config.get("llm_provider", "gemini").lower()
            max_tokens = model_config.get("max_tokens", 500)

            t2 = time.time()

            if llm_provider == "openai":
                from openai import OpenAI
                client = OpenAI(api_key=llm_api_key)

                response = client.chat.completions.create(
                    model=model_config.get("llm_model_name"),
                    messages=[
                        {"role": "system", "content": "Answer only from the provided context. Keep the response concise and factual."},
                        {"role": "user", "content": context + "\n\nQuestion: " + question}
                    ],
                    max_tokens=max_tokens
                )

                answer = response.choices[0].message.content or ""

            else:
                llm = GeminiProvider(
                    model=model_config.get("llm_model_name"),
                    api_key=llm_api_key
                )
                answer = llm.generate(
                    question=f"""Answer only from the context below and keep the response concise.

Context:
{context}

Question: {question}""",
                    context=top_results
                )

            print("DEBUG llm answer time:", time.time() - t2)

        def extract_field(text: str, field_name: str) -> str:
            pattern = rf"{re.escape(field_name)}:\s*(.+)"
            match = re.search(pattern, text, re.IGNORECASE)
            return match.group(1).strip() if match else ""

        tickets = []

        for r in top_results:
            meta = r.get("metadata", {}) or {}
            text = str(meta.get("text") or "")

            ticket_id = extract_field(text, "Issue Key")
            issue_type = extract_field(text, "Type")
            summary = extract_field(text, "Summary")
            status = extract_field(text, "Status")
            priority = extract_field(text, "Priority")
            detailed_description = extract_field(text, "Detailed Description")
            resolution_name = extract_field(text, "Resolution")
            comments_raw = extract_field(text, "Comments")  # ✅ added

            source_value = (
                meta.get("source_name")
                or meta.get("source_type")
                or meta.get("collection")
                or ""
            )

            if not source_value:
                source_url = str(meta.get("source_url") or "").lower()
                if "atlassian.net" in source_url:
                    source_value = "Jira"
                elif "sharepoint" in source_url:
                    source_value = "SharePoint"
                elif source_url.startswith("c:\\") or source_url.startswith("/") or source_url.startswith("\\\\"):
                    source_value = "Local SharePoint"

            summary_value = summary.strip()
            detailed_value = detailed_description.strip()
            resolution_name_value = resolution_name.strip()
            status_lower = str(status or "").lower().strip()  # ✅ define early

            source_type_lower = str(source_value).lower()


            if source_type_lower == "jira":
                description = summary_value or text[:200]

                jira_status_words = {"done", "fixed", "won't fix", "duplicate",
                                     "cannot reproduce", "incomplete", ""}

                resolution = detailed_value or ""

                # Only use comments as resolution fallback for CLOSED tickets
                # Open tickets should never show comments as resolution
                is_closed = status_lower not in {
                    "to do", "open", "in progress", "in review",
                    "reopened", "pending", "new", "assigned", "on hold"
                }

                if is_closed and (not resolution or resolution.lower() in jira_status_words):
                    # Extract reason from comment: "Reason: <resolution text>"
                    reason_match = re.search(r"Reason:\s*(.+?)(?:\s*\||\s*$)", comments_raw, re.IGNORECASE)
                    if reason_match:
                        resolution = reason_match.group(1).strip()
                    elif comments_raw:
                        resolution = comments_raw.strip()

                # If still just a status word, clear it
                if resolution.lower() in jira_status_words:
                    resolution = ""

            elif "sharepoint" in source_type_lower:
                description = detailed_value or summary_value or text[:200]

                resolution = ""

                # ✅ Extract multi-line resolution block
                resolution_match = re.search(
                    r"(?ims)Resolution(?: Notes)?\s*:\s*(.*?)(?:\n[A-Z][a-zA-Z ]+:\s*|\Z)",
                    text
                )

                if resolution_match:
                    resolution = resolution_match.group(1).strip()

                # fallback: try workaround
                if not resolution:
                    workaround_match = re.search(
                        r"(?ims)Workaround\s*:\s*(.*?)(?:\n[A-Z][a-zA-Z ]+:\s*|\Z)",
                        text
                    )
                    if workaround_match:
                        resolution = workaround_match.group(1).strip()

                # fallback: empty (DO NOT return full text)
                if not resolution:
                    resolution = ""

            else:
                description = detailed_value or summary_value or text[:200]
                resolution = resolution_name_value or ""

            root_cause = ""
            root_cause_match = re.search(r"(?im)^Root Cause:\s*(.+)$", text)
            if root_cause_match:
                root_cause = root_cause_match.group(1).strip()

            # ✅ For open tickets — include in results but blank resolution + confidence
            open_statuses = {
                "to do", "open", "in progress", "in review",
                "reopened", "pending", "new", "assigned", "on hold"
            }
            is_open = status_lower in open_statuses
            if is_open:
                resolution = ""
                root_cause = ""

            tickets.append({
                "source": str(source_value or ""),
                "ticket_id": str(ticket_id or ""),
                "ticket_description": str(description or ""),
                "resolution": str(resolution or "") if not is_open else "",
                "root_cause": str(root_cause or "") if not is_open else "",
                "issue_type": str(issue_type or ""),
                "status": str(status or ""),
                "priority": str(priority or ""),
                "confidence_score": float(r.get("score") or 0) if not is_open else None,
                "source_url": meta.get("source_url"),
            })

        return {
            "answer": answer,
            "tickets": tickets,
            "results": top_results,
            "context": context,
            "generate_answer": generate_answer
        }

    def extract(self, source: Dict, config: Dict) -> List[Dict]:
        source_type = (source.get("source_type") or "").lower()

        if source_type == "jira":
            return self.jira_ingestor.extract(source)

        if source_type == "sharepoint_local":
            return self.sharepoint_local_ingestor.extract(source)

        if source_type == "sharepoint":
            print("SharePoint API ingestion is currently bypassed because Azure AD credentials are not available.")
            return []

        raise ValueError(f"Unsupported source type: {source_type}")

    def chunk(self, docs: List[Dict], source: Dict) -> List[Dict]:
        chunks = []
        print("DEBUG: chunk() called")

        for doc in docs:
            if isinstance(doc, dict):
                text = str(doc.get("text") or "")
                metadata = doc
            else:
                text = str(doc)
                metadata = {}

            if not text.strip():
                continue

            chunks.append({
                "id": self._generate_id(text),
                "text": text,
                "metadata": {
                    "source_name": source.get("source_name"),
                    "source_type": source.get("source_type"),
                    "source_url": str(source.get("source_url")),
                    **metadata,
                }
            })

        print("DEBUG: chunk() successfully called")
        return chunks

    def embed(self, chunks: List[Dict], config: Dict) -> List[Dict]:
        texts = [c["text"] for c in chunks if c.get("text")]

        model_config = config.get("models", {})
        embedding_model = model_config.get("embedding_model_name")
        if not embedding_model:
            raise ValueError("Embedding model is missing in config: models.embedding_model_name")

        secrets = config.get("secrets", {})
        api_key = secrets.get("embedding_api_key")
        if not api_key:
            raise ValueError("Embedding API key is missing in config: secrets.embedding_api_key")

        vectors = self.embedding_client.embed_documents(
            texts,
            {
                "model": embedding_model,
                "provider": model_config.get("embedding_provider", "gemini")
            },
            api_key
        )

        if len(vectors) != len(texts):
            raise ValueError(
                f"Embedding count mismatch. texts={len(texts)}, vectors={len(vectors)}"
            )

        vector_index = 0
        embedded_chunks = []

        for chunk in chunks:
            if not chunk.get("text"):
                continue

            chunk["embedding"] = vectors[vector_index]
            embedded_chunks.append(chunk)
            vector_index += 1

        return embedded_chunks

    def store(self, vectors: List[Dict], source: Dict, tenant_id: str):
        collection = f"{tenant_id}_{source.get('collection_name', 'default')}"

        formatted = [
            {
                "values": v["embedding"],
                "metadata": {
                    **v["metadata"],
                    "tenant_id": tenant_id,
                    "collection": collection,
                    "source_type": source.get("source_type", ""),
                    "source_name": source.get("source_name", ""),
                    "source_url": source.get("source_url", ""),
                    "text": v["text"],
                },
            }
            for v in vectors
        ]

        self.vector_db.upsert(collection, formatted)

    def _generate_id(self, text: str):
        return hashlib.md5(text.encode()).hexdigest()