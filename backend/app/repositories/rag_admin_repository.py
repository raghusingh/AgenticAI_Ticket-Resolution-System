import json
from pathlib import Path


class RagAdminRepository:
    def __init__(self):
        self.base_dir = Path(__file__).resolve().parents[2]
        self.config_dir = self.base_dir / "config_store"
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, tenant_id: str) -> Path:
        return self.config_dir / f"{tenant_id}_rag_config.json"

    def _default_config(self, tenant_id: str) -> dict:
        return {
            "tenant_id": tenant_id,
            "models": {},
            "data_sources": [],
            "secrets": {},
            "theme": {},
        }

    def get_setup(self, tenant_id: str) -> dict:
        file_path = self._file_path(tenant_id)
        if not file_path.exists():
            return self._default_config(tenant_id)

        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, tenant_id: str, data: dict) -> dict:
        file_path = self._file_path(tenant_id)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return data

    def save_models(self, tenant_id: str, models_payload: dict) -> dict:
        config = self.get_setup(tenant_id)
        config["models"] = models_payload
        return self._save(tenant_id, config)

    def save_secrets(self, tenant_id: str, secrets_payload: dict) -> dict:
        config = self.get_setup(tenant_id)
        config["secrets"] = {
            **config.get("secrets", {}),
            **secrets_payload,
        }
        return self._save(tenant_id, config)

    def add_data_source(self, tenant_id: str, source_payload: dict) -> dict:
        config = self.get_setup(tenant_id)
        sources = config.get("data_sources", [])

        source_type = (source_payload.get("source_type") or "").strip().lower()

        new_sources = []
        replaced = False

        for src in sources:
            existing_type = (src.get("source_type") or "").strip().lower()

            if existing_type == source_type:
                new_sources.append({
                    **src,
                    **source_payload,
                })
                replaced = True
            else:
                new_sources.append(src)

        if not replaced:
            new_sources.append(source_payload)

        config["data_sources"] = new_sources
        return self._save(tenant_id, config)