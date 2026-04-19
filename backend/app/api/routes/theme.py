from fastapi import APIRouter, HTTPException
from app.repositories.ai_config_repository import AIConfigRepository

router = APIRouter(prefix="/api/v1/theme", tags=["theme"])


@router.get("/{tenant_id}")
def get_theme(tenant_id: str):
    repo = AIConfigRepository()
    config = repo.get_tenant_config(tenant_id)

    if not config:
        raise HTTPException(status_code=404, detail="Tenant config not found")

    return config.get("theme", {
        "theme_name": "default",
        "primary_color": "#2563eb",
        "background_color": "#ffffff",
        "text_color": "#111827",
    })