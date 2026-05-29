from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    telegram_bot_token: str = Field(..., description="Token from @BotFather")

    anthropic_api_key: str = Field(..., description="Anthropic API key")
    model_name: str = Field(
        default="claude-opus-4-8",
        description="Model name (claude-opus-4-8, claude-sonnet-4-6, etc.)",
    )
    enable_prompt_caching: bool = Field(
        default=True,
        description="Enable prompt caching for system prompts",
    )

    database_url: str = Field(
        default="postgresql+asyncpg://bot:bot@localhost:5432/content_agent"
    )

    log_level: str = Field(default="INFO")
    admin_telegram_chat_id: str = Field(default="", description="Chat for CRITICAL alerts")
    telegram_payment_token: str = Field(default="", description="Payment provider token from BotFather")

    free_generations: int = Field(default=3, ge=0)
    subscription_price_rub: int = Field(default=2499, ge=1)
    rate_limit_per_hour: int = Field(default=1, ge=1)
    max_rewrites_per_post: int = Field(default=3, ge=0)
    scraper_timeout_seconds: int = Field(default=15, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
