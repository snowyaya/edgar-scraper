"""
All values are read from environment variables (injected by Docker Compose
via the .env file). 
Defaults are set for local development.
"""

from functools import lru_cache
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- PostgreSQL connection ---
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="edgar")
    postgres_user: str = Field(default="edgar_user")
    postgres_password: str = Field(default="changeme")

    @computed_field
    @property
    def database_url(self) -> str:
        """
        Async URL for SQLAlchemy (asyncpg driver)
        """
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def database_url_sync(self) -> str:
        """
        Sync URL for Alembic migrations
        """
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # --- SEC EDGAR ---
    # https://www.sec.gov/os/accessing-edgar-data
    sec_user_agent: str = Field(
        description="SEC requires a real name and email in the User-Agent header."
    )

    # --- Crawler behaviour ---
    # A short delay between HTTP requests in seconds
    crawl_delay_seconds: float = Field(default=0.5)
    # Per-request timeout in seconds
    request_timeout_seconds: float = Field(default=30.0)
    # Max retry attempts
    max_retries: int = Field(default=3)
    # Max concurrent HTTP requests in flight
    max_concurrent_requests: int = Field(default=5)
    # Minimum word count to consider a page worth storing
    min_content_words: int = Field(default=50)

    log_level: str = Field(default="INFO")


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Module-level singleton
settings = get_settings()
