"""Configuration for supplier-finder."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


@lru_cache
def get_settings():
    """Get cached settings."""
    return _Settings()


class _Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_file=".env")

    # Database
    db_dsn: str = "postgresql://postgres:postgres@localhost:5432/tender"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Streams
    stream_rfq: str = "new_rfq"
    stream_results: str = "suppliers_found"

    # Yandex XML
    yandex_xml_user: str = ""
    yandex_xml_key: str = ""

    # Limits
    max_urls_per_item: int = 8
    max_concurrent_parsers: int = 4
    item_concurrency: int = 3
