from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Micromega Inmobiliaria"
    app_env: str = "dev"
    database_url: str = "sqlite:///./micromega.db"

    llm_provider: str = "mock"  # mock | openai
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"

    whatsapp_verify_token: str = "micromega-dev-token"
    whatsapp_access_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_graph_api_version: str = "vXX.X"
    meta_app_secret: str | None = None

    auto_reply_enabled: bool = True
    human_handoff_keyword: str = "humano"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
