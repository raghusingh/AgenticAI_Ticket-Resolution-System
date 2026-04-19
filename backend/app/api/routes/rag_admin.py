from fastapi import APIRouter
from app.schemas.rag_admin import (
    ModelConfigRequest,
    DataSourceRequest,
    SecretConfigRequest,
    RagSetupResponse,
)
from app.repositories.rag_admin_repository import RagAdminRepository
from app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/api/v1/admin/rag-config", tags=["rag-admin"])

repo = RagAdminRepository()
ingestion_service = IngestionService(repo)


@router.get("/{tenant_id}", response_model=RagSetupResponse)
def get_rag_setup(tenant_id: str):
    return repo.get_setup(tenant_id)


@router.post("/models/{tenant_id}", response_model=RagSetupResponse)
def save_model_config(tenant_id: str, request: ModelConfigRequest):
    return repo.save_models(tenant_id, request.model_dump(exclude_none=True))


@router.post("/sources/{tenant_id}", response_model=RagSetupResponse)
def save_data_source(tenant_id: str, request: DataSourceRequest):
    return repo.add_data_source(tenant_id, request.model_dump(exclude_none=True))


@router.post("/secrets/{tenant_id}", response_model=RagSetupResponse)
def save_secret_config(tenant_id: str, request: SecretConfigRequest):
    return repo.save_secrets(tenant_id, request.model_dump(exclude_none=True))


@router.post("/sources/{tenant_id}/test")
def test_source_connection(tenant_id: str, request: DataSourceRequest):
    source_type = (request.source_type or "").lower()

    if source_type == "jira":
        return {
            "tenant_id": tenant_id,
            "ok": True,
            "message": f"Jira connection test simulated for project '{request.project_key or request.api_key or ''}'.",
            "source_url": request.source_url,
        }

    if source_type == "sharepoint":
        return {
            "tenant_id": tenant_id,
            "ok": True,
            "message": f"SharePoint connection test simulated for site '{request.site_id or ''}'.",
            "source_url": request.source_url,
        }

    if source_type == "sharepoint_local":
        return {
            "tenant_id": tenant_id,
            "ok": True,
            "message": f"Local SharePoint folder test simulated for path '{request.source_url}'.",
            "source_url": request.source_url,
        }

    return {
        "tenant_id": tenant_id,
        "ok": False,
        "message": f"Unsupported source type: {request.source_type}",
        "source_url": request.source_url,
    }


@router.post("/secrets/{tenant_id}/test")
def test_secret_connection(tenant_id: str, request: SecretConfigRequest):
    has_key = bool(request.llm_api_key)
    return {
        "tenant_id": tenant_id,
        "ok": has_key,
        "message": "LLM API key provided." if has_key else "LLM API key is missing.",
    }


# ✅ Ingest API
@router.post("/ingest/{tenant_id}")
def run_ingestion(tenant_id: str):
    return ingestion_service.run(tenant_id)