"""Copywriter Agent: angle дня + платформа + профиль → готовый пост.

Один класс на 4 платформы — отличаются только system-промптами (`prompts/{platform}.txt`).
"""
import logging
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError

from app.agents.schemas import DayPlan, GeneratedPost
from app.agents.strategist import _format_profile
from app.db.models import Platform, UserProfile
from app.services.llm import LLMClient, LLMError, get_llm_client

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

_PLATFORM_PROMPT_FILES: dict[Platform, str] = {
    Platform.TELEGRAM: "telegram.txt",
    Platform.VK: "vk.txt",
    Platform.STORIES: "stories.txt",
}


@lru_cache(maxsize=8)
def _load_prompt(platform: Platform) -> str:
    filename = _PLATFORM_PROMPT_FILES[platform]
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _build_user_prompt(
    *,
    day_plan: DayPlan,
    profile: UserProfile | None,
    week_theme: str,
    extra_directive: str = "",
) -> str:
    base = (
        f"# Профиль автора\n{_format_profile(profile)}\n\n"
        f"# Контекст недели\n"
        f"Общая тема недели: {week_theme}\n\n"
        f"# Этот день\n"
        f"День {day_plan.day} из 7\n"
        f"Тип поста: {day_plan.post_type.value}\n"
        f"Angle (центральная идея): {day_plan.angle}\n"
        f"Hook (предложенная цепляющая фраза): {day_plan.hook}\n"
        + (f"Заметка стратега: {day_plan.rationale}\n" if day_plan.rationale else "")
        + "\nНапиши один пост по этому angle с учётом профиля автора. "
        "Верни строго JSON по схеме."
    )
    if extra_directive:
        base += f"\n\n# Дополнительная директива\n{extra_directive}"
    return base


async def write_post(
    *,
    day_plan: DayPlan,
    platform: Platform,
    profile: UserProfile | None,
    week_theme: str,
    extra_directive: str = "",
    client: LLMClient | None = None,
) -> GeneratedPost:
    """Сгенерировать пост под платформу. Кидает `LLMError` или `ValidationError`."""
    llm = client or get_llm_client()

    system = _load_prompt(platform)
    user = _build_user_prompt(
        day_plan=day_plan, profile=profile, week_theme=week_theme, extra_directive=extra_directive
    )

    log.info(
        "copywriter: day=%d type=%s platform=%s",
        day_plan.day,
        day_plan.post_type.value,
        platform.value,
    )

    raw = await llm.complete_json(
        system=system,
        user=user,
        temperature=0.85,  # повыше — разнообразие лучше для копирайтинга
        max_tokens=2000,
    )

    try:
        post = GeneratedPost.model_validate(raw)
    except ValidationError as e:
        log.error("copywriter: schema validation failed for %s: %s", platform.value, e)
        raise LLMError(
            "llm_invalid_schema",
            f"GeneratedPost validation failed for {platform.value}: {e}",
        ) from e

    log.info(
        "copywriter: ok platform=%s len=%d hashtags=%d",
        platform.value,
        len(post.content),
        len(post.hashtags),
    )
    return post
