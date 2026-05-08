"""Сквозной live-демо всей цепочки: URL → Scraper → Strategist → Copywriter (×4).
Запуск: uv run python scripts/live_demo.py
"""
import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from app.agents.copywriter import write_post
from app.agents.scraper import scrape
from app.agents.strategist import plan_week
from app.db.models import Platform, Tone, UserProfile

URL = "https://habr.com/ru/articles/780002/"
PLATFORMS = [Platform.TELEGRAM, Platform.VK, Platform.STORIES]


async def main() -> None:
    print("─" * 70)
    print("1. SCRAPER — извлекаем тезисы из статьи")
    print("─" * 70)
    scraped = await scrape(URL)
    print(f"  title: {scraped.title}")
    print(f"  theses: {len(scraped.theses)}")

    profile = UserProfile(
        user_id=1,
        niche="SMM для малого бизнеса",
        tone=Tone.FRIENDLY,
        forbidden=["политика", "крипта"],
        formats=["Истории", "Кейсы"],
        example_posts=[],
    )

    print()
    print("─" * 70)
    print("2. STRATEGIST — собирает 7-дневный план")
    print("─" * 70)
    plan = await plan_week(scraped, profile, [p.value for p in PLATFORMS])
    print(f"  тема: {plan.theme}")

    # Берём только день 3 (expertise) для демо — экономим токены
    target_day = next(d for d in plan.days if d.day == 3)
    print(f"  день 3 angle: {target_day.angle[:80]}...")

    print()
    print("─" * 70)
    print(f"3. COPYWRITER × {len(PLATFORMS)} платформ — день 3")
    print("─" * 70)

    posts = await asyncio.gather(
        *(
            write_post(
                day_plan=target_day, platform=p, profile=profile, week_theme=plan.theme
            )
            for p in PLATFORMS
        )
    )

    for platform, post in zip(PLATFORMS, posts):
        print()
        print("=" * 70)
        print(f" {platform.value.upper()}  ({len(post.content)} симв)")
        print("=" * 70)
        print(post.content)
        print()
        if post.hashtags:
            print(f"  Хэштеги: {' '.join(post.hashtags)}")
        if post.cta:
            print(f"  CTA: {post.cta}")
        if post.rec_time:
            print(f"  Время: {post.rec_time}")


if __name__ == "__main__":
    asyncio.run(main())
