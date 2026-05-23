"""Configuration with pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_file=".env")

    # Database
    db_dsn: str

    # Redis
    redis_url: str

    # HTTP
    http_port: int = 8080

    # Configuration
    margin_percent: float = 15.0
    report_dir: str = "./reports"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
