from typing import List, Optional
from pydantic import BaseModel, Field


class ModelConfigRequest(BaseModel):
    llm_provider: str
    llm_model_name: str
    embedding_provider: str
    embedding_model_name: str
    temperature: float = 0.2
    top_k: int = 5
    max_tokens: int = 1000


class DataSourceRequest(BaseModel):
    # common
    source_name: str = ""
    source_type: str = "jira"
    source_url: str = ""
    auth_type: str = "basic"
    chunk_size: int = 1000
    chunk_overlap: int = 150
    collection_name: str = "KB_All"
    is_enabled: bool = True
    sync_frequency: str = "daily"

    # jira
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    api_key: Optional[str] = None
    project_key: Optional[str] = None
    jql: Optional[str] = None
    issue_start: Optional[int] = None
    issue_end: Optional[int] = None

    # sharepoint
    site_id: Optional[str] = None
    drive_id: Optional[str] = None
    list_id: Optional[str] = None
    folder_id: Optional[str] = None
    folder_path: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    tenant_id_secret: Optional[str] = None


class SecretConfigRequest(BaseModel):
    llm_api_key: Optional[str] = None
    embedding_api_key: Optional[str] = None
    vector_db_api_key: Optional[str] = None

    sharepoint_tenant_id: Optional[str] = None
    sharepoint_client_id: Optional[str] = None
    sharepoint_client_secret: Optional[str] = None


class RagSetupResponse(BaseModel):
    tenant_id: str
    models: dict = Field(default_factory=dict)
    data_sources: List[dict] = Field(default_factory=list)
    secrets: dict = Field(default_factory=dict)
    theme: dict = Field(default_factory=dict)