"""Pydantic-схемы для валидации ответов агентов."""
from pydantic import BaseModel, Field, field_validator

from app.db.models import Platform, PostType


class DayPlan(BaseModel):
    """Один день недельного плана — что и зачем постим."""

    day: int = Field(..., ge=1, le=7)
    post_type: PostType
    angle: str = Field(..., min_length=10, max_length=500, description="Центральная идея дня")
    hook: str = Field(..., min_length=5, max_length=200, description="Цепляющая фраза/заголовок")
    rationale: str = Field(default="", max_length=500, description="Почему именно это в этот день")


class WeekPlan(BaseModel):
    """Недельный план — общая тема + 7 дней с воронкой engagement→expertise→trust→sale."""

    theme: str = Field(..., min_length=5, max_length=200, description="Общая тема недели")
    days: list[DayPlan] = Field(..., min_length=7, max_length=7)

    @field_validator("days")
    @classmethod
    def _check_days_complete(cls, v: list[DayPlan]) -> list[DayPlan]:
        days_seen = sorted(d.day for d in v)
        if days_seen != [1, 2, 3, 4, 5, 6, 7]:
            raise ValueError(f"days must cover 1..7 exactly once, got {days_seen}")
        return sorted(v, key=lambda d: d.day)


class GeneratedPost(BaseModel):
    """Готовый пост от Copywriter Agent под конкретную платформу."""

    content: str = Field(..., min_length=10, max_length=8000)
    hashtags: list[str] = Field(default_factory=list, max_length=10)
    cta: str = Field(default="", max_length=300)
    rec_time: str = Field(default="", max_length=80, description='"10:00", "вечер будни", и т.п.')

    @field_validator("hashtags")
    @classmethod
    def _normalize_hashtags(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for tag in v:
            t = tag.strip()
            if not t:
                continue
            if not t.startswith("#"):
                t = "#" + t
            t = t.replace(" ", "")
            out.append(t)
        return out
