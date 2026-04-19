from typing import Any, Dict, List
from app.contracts.vector_store_provider import VectorStoreProvider


class FAISSProvider(VectorStoreProvider):
    def __init__(self, index_path: str, embedding_provider):
        self.index_path = index_path
        self.embedding_provider = embedding_provider
        self.docs: List[Dict[str, Any]] = []

    def upsert(self, documents: List[Dict[str, Any]]) -> None:
        self.docs.extend(documents)

    def similarity_search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        return self.docs[:k]

    def delete_by_source(self, source: str) -> None:
        self.docs = [d for d in self.docs if d.get("metadata", {}).get("source") != source]

    def health(self) -> Dict[str, Any]:
        return {"status": "ok", "vector_store": "faiss", "note": "stub implementation"}
