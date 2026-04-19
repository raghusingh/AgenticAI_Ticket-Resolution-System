from typing import List
from sentence_transformers import SentenceTransformer
from app.contracts.embedding_provider import EmbeddingProvider


class HuggingFaceEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str):
        self._model = model
        self.client = SentenceTransformer(model)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.client.encode(texts).tolist()

    def embed_query(self, text: str) -> List[float]:
        return self.client.encode([text])[0].tolist()

    def model_name(self) -> str:
        return self._model
