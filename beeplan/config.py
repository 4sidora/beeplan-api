from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg2://beeplan:beeplan@localhost:5432/beeplan"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    builder_url: str = "http://localhost:9000"
    builder_secret: str = "dev-builder-secret"
    firmware_build_ttl_minutes: int = 60
    firmware_builds_per_hour: int = 10
    public_api_base_url: str = "http://localhost:8000"


def get_settings() -> Settings:
    return Settings()
