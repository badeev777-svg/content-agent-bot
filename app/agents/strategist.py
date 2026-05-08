"""Strategist Agent: тезисы конкурента + профиль → 7-дневный план постов."""
import logging
from pathlib import Path

from pydantic import ValidationError

from app.agents.scraper import ScrapedContent
from app.agents.schemas import WeekPlan
from app.db.models import UserProfile
from app.services.llm import LLMClient, LLMError, get_llm_client

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "strategist.txt"


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _format_profile(profile: UserProfile | None) -> str:
    if profile is None or not profile.niche:
        return "Профиль не настроен."
    parts = [
        f"- Ниша: {profile.niche}",
        f"- Тон: {profile.tone.value if profile.tone else 'не указан'}",
        f"- Табу: {', '.join(profile.forbidden) if profile.forbidden else 'нет'}",
        f"- Любимые форматы: {', '.join(profile.formats) if profile.formats else 'не указаны'}",
    ]
    if profile.style_notes:
        parts.append(f"- Заметки о стиле: {profile.style_notes}")
    if profile.example_posts:
        joined = "\n---\n".join(profile.example_posts[:3])
        parts.append(f"- Примеры постов автора:\n{joined}")
    return "\n".join(parts)


def _build_user_prompt(
    scraped: ScrapedContent, profile: UserProfile | None, platforms: list[str]
) -> str:
    theses = "\n".join(f"- {t}" for t in scraped.theses) or "— тезисы не извлечены"
    return (
        f"# Профиль автора\n{_format_profile(profile)}\n\n"
        f"# Платформы для публикации\n{', '.join(platforms)}\n\n"
        f"# Материал-источник\n"
        f"URL: {scraped.url}\n"
        f"Заголовок: {scraped.title}\n"
        f"Тема: {scraped.theme}\n"
        f"Тезисы:\n{theses}\n\n"
        "Сделай недельный план постов в стиле автора, опираясь на тезисы материала. "
        "Верни строго JSON по схеме."
    )


async def plan_week(
    scraped: ScrapedContent,
    profile: UserProfile | None,
    platforms: list[str],
    *,
    client: LLMClient | None = None,
) -> WeekPlan:
    """Сгенерировать недельный план. Кидает `LLMError` или `ValidationError`."""
    llm = client or get_llm_client()

    system = _load_system_prompt()
    user = _build_user_prompt(scraped, profile, platforms)

    log.info(
        "strategist: planning week url=%s platforms=%s niche=%s",
        scraped.url,
        platforms,
        profile.niche if profile else None,
    )

    raw = await llm.complete_json(system=system, user=user, temperature=0.7, max_tokens=4000)
    try:
        plan = WeekPlan.model_validate(raw)
    except ValidationError as e:
        log.error("strategist: schema validation failed: %s", e)
        raise LLMError(
            "llm_invalid_schema",
            f"WeekPlan validation failed: {e}",
        ) from e

    log.info("strategist: ok theme=%r days=%d", plan.theme[:60], len(plan.days))
    return plan
