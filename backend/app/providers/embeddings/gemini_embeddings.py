from typing import List
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from app.contracts.embedding_provider import EmbeddingProvider


class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, model: str):
        self._model = model
        self.client = GoogleGenerativeAIEmbeddings(model=model, google_api_key=api_key)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.client.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        return self.client.embed_query(text)

    def model_name(self) -> str:
        return self._model
