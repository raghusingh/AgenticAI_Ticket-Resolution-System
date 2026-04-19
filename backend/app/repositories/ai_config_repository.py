import json
from pathlib import Path


class AIConfigRepository:
    def get_tenant_config(self, tenant_id: str) -> dict:
        base_dir = Path(__file__).resolve().parents[2]
        file_path = base_dir / "config_store" / f"{tenant_id}_rag_config.json"
        print("CONFIG PATH:", file_path)
        print("FILE EXISTS:", file_path.exists())
        if not file_path.exists():
            return {}

        with open(file_path, "r", encoding="utf-8") as f:
            raw_config = json.load(f)

        models = raw_config.get("models", {})
        secrets = raw_config.get("secrets", {})
        data_sources = raw_config.get("data_sources", [])
        if data_sources:
            collection_name = data_sources[0].get("collection_name", "default")

        return {
            "tenant_id": tenant_id,
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
            "vector_store": {
                "provider": "faiss",
                "index_path": f"faiss_store/{tenant_id}_{collection_name}.index",
            },
            "theme": raw_config.get("theme", {
                "theme_name": "default",
                "primary_color": "#2563eb",
                "background_color": "#ffffff",
                "text_color": "#111827",
            }),
        }