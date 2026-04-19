from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ChatOps RAG Product"
    app_env: str = "dev"
    api_prefix: str = "/api/v1"
    google_api_key: str | None = None
    openai_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
