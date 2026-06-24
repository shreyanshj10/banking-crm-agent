"""Application configuration.

All settings are loaded from environment variables (or a local `.env` file).
Nothing is hardcoded — secrets and connection strings must come from the
environment. See `.env.example` for the documented variables.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings, sourced from the environment / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # PostgreSQL connection — async driver form, e.g.
    #   postgresql+asyncpg://user:pass@host:5432/dbname
    database_url: str

    # Anthropic API key — never hardcoded; provided via the environment.
    anthropic_api_key: str

    # Single model for the whole system. One-line swap hook: either can be
    # overridden via .env with no code change. Bare dateless ID (no date suffix).
    anthropic_model: str = "claude-opus-4-8"
    anthropic_message_model: str = "claude-opus-4-8"


settings = Settings()
