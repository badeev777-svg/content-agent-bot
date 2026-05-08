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

    openrouter_api_key: str = Field(..., description="OpenRouter API key (sk-or-...)")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")
    model_name: str = Field(
        default="anthropic/claude-sonnet-4.6",
        description="Имя модели в формате OpenRouter: provider/model-name",
    )
    enable_prompt_caching: bool = Field(
        default=True,
        description="Cache_control для системных промптов (Anthropic-модели)",
    )
    openrouter_app_name: str = Field(
        default="Content Agent Bot",
        description="X-Title заголовок (обязателен для OpenRouter free tier)",
    )
    openrouter_app_url: str = Field(
        default="https://github.com/badeev777-svg/content-agent-bot",
        description="HTTP-Referer заголовок",
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
