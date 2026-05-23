"""Configuration with pydantic-settings."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    vk_group_token: str
    vk_group_id: int
    vk_secret: str = ""
    vk_confirmation: str = ""

    db_dsn: str
    redis_url: str
    report_service_url: str

    admin_vk_ids: list[int] = []

    @field_validator("admin_vk_ids", mode="before")
    @classmethod
    def parse_admin_vk_ids(cls, v):
        if isinstance(v, list):
            return v
        if v is None:
            return []
        if isinstance(v, str):
            if not v.strip():
                return []
            try:
                return [int(x.strip()) for x in v.split(",") if x.strip()]
            except Exception:
                return []
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
