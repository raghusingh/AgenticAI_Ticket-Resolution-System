from fastapi import APIRouter, HTTPException
from app.repositories.ai_config_repository import AIConfigRepository
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag_service import RAGService

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("")
def chat(request: ChatRequest):
    repo = AIConfigRepository()
    raw_config = repo.get_tenant_config(request.tenant_id)

    if not raw_config:
        raise HTTPException(status_code=404, detail="Tenant config not found")

    # Case 1: repository returns raw tenant JSON
    if "models" in raw_config:
        models = raw_config.get("models", {})
        secrets = raw_config.get("secrets", {})

        tenant_config = {
            "tenant_id": raw_config.get("tenant_id"),
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
                "index_path": "faiss_store/index",
            },
            "theme": raw_config.get("theme", {}),
        }

    # Case 2: repository already returns normalized config
    else:
        llm = raw_config.get("llm", {})
        embedding = raw_config.get("embedding", {})
        vector_store = raw_config.get("vector_store", {})

        tenant_config = {
            "tenant_id": raw_config.get("tenant_id"),
            "llm": {
                "provider": (llm.get("provider") or "").lower(),
                "model": llm.get("model"),
                "api_key": llm.get("api_key"),
                "temperature": llm.get("temperature", 0.2),
                "max_tokens": llm.get("max_tokens", 1000),
            },
            "embedding": {
                "provider": (embedding.get("provider") or "").lower(),
                "model": embedding.get("model"),
                "api_key": embedding.get("api_key"),
            },
            "vector_store": {
                "provider": vector_store.get("provider", "faiss"),
                "index_path": vector_store.get("index_path", "faiss_store/index"),
            },
            "theme": raw_config.get("theme", {}),
        }

    if not tenant_config["llm"].get("api_key"):
        raise HTTPException(
            status_code=500,
            detail="Missing llm.api_key in tenant config returned by AIConfigRepository",
        )

    if not tenant_config["embedding"].get("api_key"):
        raise HTTPException(
            status_code=500,
            detail="Missing embedding.api_key in tenant config returned by AIConfigRepository",
        )
    print(tenant_config)
    rag_service = RAGService(tenant_config)
    result = rag_service.ask(request.question, request.top_k or 5)
    return ChatResponse(**result)