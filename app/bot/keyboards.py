from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import Platform, Tone

TONE_OPTIONS: list[tuple[Tone, str]] = [
    (Tone.EXPERT, "🎓 Экспертный"),
    (Tone.FRIENDLY, "🤝 Дружеский"),
    (Tone.PROVOCATIVE, "🔥 Провокационный"),
]

FORMAT_OPTIONS: list[tuple[str, str]] = [
    ("lists", "Списки"),
    ("stories", "Истории"),
    ("facts", "Факты"),
    ("cases", "Кейсы"),
]

PLATFORM_OPTIONS: list[tuple[Platform, str]] = [
    (Platform.TELEGRAM, "Telegram"),
    (Platform.VK, "ВКонтакте"),
    (Platform.STORIES, "Истории"),
    (Platform.DZEN, "Яндекс Дзен"),
]


def tone_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, callback_data=f"tone:{t.value}")] for t, label in TONE_OPTIONS]
    return InlineKeyboardMarkup(rows)


def formats_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    def label(key: str, name: str) -> str:
        mark = "✅" if key in selected else "⬜"
        return f"{mark} {name}"

    rows = [
        [InlineKeyboardButton(label(k, n), callback_data=f"fmt:{k}")] for k, n in FORMAT_OPTIONS
    ]
    rows.append([InlineKeyboardButton("✓ Готово", callback_data="fmt:done")])
    return InlineKeyboardMarkup(rows)


def skip_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Пропустить", callback_data=callback_data)]])


def platforms_keyboard(selected: set[Platform]) -> InlineKeyboardMarkup:
    def label(p: Platform, name: str) -> str:
        mark = "✅" if p in selected else "⬜"
        return f"{mark} {name}"

    rows = [
        [InlineKeyboardButton(label(p, n), callback_data=f"plat:{p.value}")]
        for p, n in PLATFORM_OPTIONS
    ]
    rows.append([InlineKeyboardButton("🚀 Запустить", callback_data="plat:go")])
    rows.append([InlineKeyboardButton("✕ Отмена", callback_data="plat:cancel")])
    return InlineKeyboardMarkup(rows)


def summary_keyboard(plan_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("📋 Весь план текстом", callback_data=f"full_plan:{plan_id}")]]
    )


def post_actions_keyboard(post_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Переписать", callback_data=f"post:rewrite:{post_id}"),
                InlineKeyboardButton("✂️ Короче", callback_data=f"post:shorter:{post_id}"),
            ],
            [
                InlineKeyboardButton("👍 Нравится", callback_data=f"post:like:{post_id}"),
                InlineKeyboardButton("👎 Не нравится", callback_data=f"post:dislike:{post_id}"),
            ],
        ]
    )
