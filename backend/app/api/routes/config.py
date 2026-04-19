from fastapi import APIRouter
from app.repositories.ai_config_repository import AIConfigRepository

router = APIRouter(prefix="/api/v1/config", tags=["config"])


@router.get("/{tenant_id}")
def get_config(tenant_id: str):
    repo = AIConfigRepository()
    return repo.get_tenant_config(tenant_id)
