from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    ContentPlan,
    Feedback,
    Platform,
    Post,
    PostType,
    Subscription,
    Tone,
    User,
    UserProfile,
)


async def get_or_create_user(
    session: AsyncSession, telegram_id: int, username: str | None = None
) -> User:
    user = await session.get(User, telegram_id)
    if user is None:
        user = User(telegram_id=telegram_id, username=username)
        session.add(user)
        await session.flush()
    elif username and user.username != username:
        user.username = username
    return user


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.get(User, telegram_id)


async def upsert_profile(
    session: AsyncSession,
    telegram_id: int,
    *,
    niche: str | None = None,
    tone: Tone | None = None,
    forbidden: list[str] | None = None,
    formats: list[str] | None = None,
    example_posts: list[str] | None = None,
    style_notes: str | None = None,
) -> UserProfile:
    profile = await session.get(UserProfile, telegram_id)
    if profile is None:
        profile = UserProfile(
            user_id=telegram_id,
            niche=niche,
            tone=tone,
            forbidden=forbidden or [],
            formats=formats or [],
            example_posts=example_posts or [],
            style_notes=style_notes,
        )
        session.add(profile)
    else:
        if niche is not None:
            profile.niche = niche
        if tone is not None:
            profile.tone = tone
        if forbidden is not None:
            profile.forbidden = forbidden
        if formats is not None:
            profile.formats = formats
        if example_posts is not None:
            profile.example_posts = example_posts
        if style_notes is not None:
            profile.style_notes = style_notes
    await session.flush()
    return profile


async def get_profile(session: AsyncSession, telegram_id: int) -> UserProfile | None:
    return await session.get(UserProfile, telegram_id)


async def increment_gens_used(session: AsyncSession, telegram_id: int) -> int:
    user = await session.get(User, telegram_id)
    if user is None:
        raise ValueError(f"user {telegram_id} not found")
    user.gens_used += 1
    await session.flush()
    return user.gens_used


async def activate_subscription(
    session: AsyncSession, telegram_id: int, days: int = 30
) -> User:
    user = await session.get(User, telegram_id)
    if user is None:
        raise ValueError(f"user {telegram_id} not found")
    user.subscription = Subscription.PAID
    user.sub_expires = datetime.now(tz=timezone.utc) + timedelta(days=days)
    await session.flush()
    return user


async def has_active_subscription(session: AsyncSession, telegram_id: int) -> bool:
    user = await session.get(User, telegram_id)
    if user is None or user.subscription != Subscription.PAID:
        return False
    if user.sub_expires is None:
        return False
    return user.sub_expires > datetime.now(tz=timezone.utc)


async def create_plan(
    session: AsyncSession,
    *,
    user_id: int,
    source_url: str,
    source_summary: str | None,
    platforms: list[str],
) -> ContentPlan:
    plan = ContentPlan(
        user_id=user_id,
        source_url=source_url,
        source_summary=source_summary,
        platforms=platforms,
    )
    session.add(plan)
    await session.flush()
    return plan


async def add_post(
    session: AsyncSession,
    *,
    plan_id: str,
    day: int,
    platform: Platform,
    post_type: PostType,
    content: str,
    hashtags: list[str] | None = None,
    cta: str | None = None,
    rec_time: str | None = None,
) -> Post:
    post = Post(
        plan_id=plan_id,
        day=day,
        platform=platform,
        post_type=post_type,
        content=content,
        hashtags=hashtags or [],
        cta=cta,
        rec_time=rec_time,
    )
    session.add(post)
    await session.flush()
    return post


async def get_recent_plans(
    session: AsyncSession, telegram_id: int, limit: int = 5
) -> list[ContentPlan]:
    result = await session.execute(
        select(ContentPlan)
        .where(ContentPlan.user_id == telegram_id)
        .order_by(ContentPlan.created_at.desc())
        .limit(limit)
        .options(selectinload(ContentPlan.posts))
    )
    return list(result.scalars().all())


async def get_plan_with_posts(
    session: AsyncSession, plan_id: str
) -> ContentPlan | None:
    result = await session.execute(
        select(ContentPlan)
        .where(ContentPlan.id == plan_id)
        .options(selectinload(ContentPlan.posts))
    )
    return result.scalar_one_or_none()


async def update_post_content(
    session: AsyncSession,
    post_id: str,
    *,
    content: str,
    hashtags: list[str],
    cta: str | None,
    rec_time: str | None,
) -> Post:
    post = await session.get(Post, post_id)
    if post is None:
        raise ValueError(f"post {post_id} not found")
    post.content = content
    post.hashtags = hashtags
    post.cta = cta
    post.rec_time = rec_time
    await session.flush()
    return post


async def set_post_feedback(
    session: AsyncSession, post_id: str, feedback: Feedback
) -> Post:
    post = await session.get(Post, post_id)
    if post is None:
        raise ValueError(f"post {post_id} not found")
    post.feedback = feedback
    await session.flush()
    return post


async def increment_rewrites(session: AsyncSession, post_id: str) -> int:
    post = await session.get(Post, post_id)
    if post is None:
        raise ValueError(f"post {post_id} not found")
    post.rewrites_used += 1
    await session.flush()
    return post.rewrites_used
