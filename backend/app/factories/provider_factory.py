from app.core.settings import settings
from app.providers.llm.gemini_provider import GeminiProvider
from app.providers.llm.openai_provider import OpenAIProvider
# from app.providers.embeddings.gemini_embeddings import GeminiEmbeddingProvider
# from app.providers.embeddings.huggingface_embeddings import HuggingFaceEmbeddingProvider
from app.providers.vectorstores.faiss_provider import FAISSProvider

from app.providers.llm.gemini_provider import GeminiProvider
from app.providers.llm.openai_provider import OpenAIProvider
from app.providers.embeddings.google_embedding_provider import GoogleEmbeddingProvider
from app.providers.embeddings.openai_embedding_provider import OpenAIEmbeddingProvider


class ProviderFactory:
    @staticmethod
    def create_llm(config: dict):
        provider = (config.get("provider") or "").lower()

        if provider == "google":
            return GeminiProvider(
                model=config.get("model"),
                api_key=config.get("api_key"),
                temperature=config.get("temperature", 0.2),
                max_tokens=config.get("max_tokens", 1000),
                top_k=config.get("top_k", 5),
                top_p=config.get("top_p", 0.9),
            )

        elif provider == "openai":
            return OpenAIProvider(
                model=config.get("model"),
                api_key=config.get("api_key"),
                temperature=config.get("temperature", 0.2),
                max_tokens=config.get("max_tokens", 1000),
            )

        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    @staticmethod
    def create_embedding(config: dict):
        provider = (config.get("provider") or "").lower()

        if provider == "google":
            return GoogleEmbeddingProvider(
                model=config.get("model"),
                api_key=config.get("api_key"),
            )

        elif provider == "openai":
            return OpenAIEmbeddingProvider(
                model=config.get("model"),
                api_key=config.get("api_key"),
            )

        else:
            raise ValueError(f"Unsupported embedding provider: {provider}")

    @staticmethod
    def create_vector_store(config: dict, embedding_provider):
        provider = config["provider"]
        if provider == "faiss":
            return FAISSProvider(
                index_path=config["index_path"],
                embedding_provider=embedding_provider,
            )
        raise ValueError(f"Unsupported vector store provider: {provider}")
