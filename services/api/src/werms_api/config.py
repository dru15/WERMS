from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    web_origin: str = "http://localhost:5173"
    database_url: str = "postgresql+asyncpg://werms:werms@localhost:5432/werms"
    redis_url: str = "redis://localhost:6379/0"
    shelter_redirect_threshold: float = Field(default=0.90, ge=0.50, le=1.0)
    route_validity_seconds: int = Field(default=300, ge=30, le=3600)
    model_mode: Literal["disabled", "approved"] = "disabled"
    model_artifact_path: str = "artifacts/models/approved"
    operational_db_path: str = "data/operational/palisades.sqlite3"
    operator_api_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
