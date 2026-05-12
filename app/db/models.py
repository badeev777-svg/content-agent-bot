import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Subscription(str, enum.Enum):
    FREE = "free"
    PAID = "paid"


class Tone(str, enum.Enum):
    EXPERT = "expert"
    FRIENDLY = "friendly"
    PROVOCATIVE = "provocative"


class Platform(str, enum.Enum):
    TELEGRAM = "telegram"
    VK = "vk"
    STORIES = "stories"
    DZEN = "dzen"


class PostType(str, enum.Enum):
    ENGAGEMENT = "engagement"
    EXPERTISE = "expertise"
    TRUST = "trust"
    SALE = "sale"


class Feedback(str, enum.Enum):
    NONE = "none"
    LIKED = "liked"
    REWRITTEN = "rewritten"


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    subscription: Mapped[Subscription] = mapped_column(
        Enum(Subscription, native_enum=False, length=16),
        default=Subscription.FREE,
        nullable=False,
    )
    gens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sub_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_gen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rewrites_used_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rewrites_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    profile: Mapped["UserProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    plans: Mapped[list["ContentPlan"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), primary_key=True
    )
    niche: Mapped[str | None] = mapped_column(Text)
    tone: Mapped[Tone | None] = mapped_column(Enum(Tone, native_enum=False, length=16))
    forbidden: Mapped[list[str]] = mapped_column(JSON, default=list)
    formats: Mapped[list[str]] = mapped_column(JSON, default=list)
    example_posts: Mapped[list[str]] = mapped_column(JSON, default=list)
    style_notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="profile")


class ContentPlan(Base):
    __tablename__ = "content_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True
    )
    source_url: Mapped[str] = mapped_column(Text)
    source_summary: Mapped[str | None] = mapped_column(Text)
    platforms: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="plans")
    posts: Mapped[list["Post"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="Post.day"
    )


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_plans.id", ondelete="CASCADE"), index=True
    )
    day: Mapped[int] = mapped_column(Integer)
    platform: Mapped[Platform] = mapped_column(Enum(Platform, native_enum=False, length=16))
    post_type: Mapped[PostType] = mapped_column(Enum(PostType, native_enum=False, length=16))
    content: Mapped[str] = mapped_column(Text)
    hashtags: Mapped[list[str]] = mapped_column(JSON, default=list)
    cta: Mapped[str | None] = mapped_column(Text)
    rec_time: Mapped[str | None] = mapped_column(String(16))
    feedback: Mapped[Feedback] = mapped_column(
        Enum(Feedback, native_enum=False, length=16),
        default=Feedback.NONE,
        nullable=False,
    )
    rewrites_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    plan: Mapped["ContentPlan"] = relationship(back_populates="posts")
