"""Единые inline-клавиатуры IrisV2."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.texts import texts


def _btn(locale: str, key: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=texts.t(locale, key), callback_data=data)


def main_menu(locale: str = "ru") -> InlineKeyboardMarkup:
    rows = [
        [_btn(locale, "btn_profile", "menu:profile"), _btn(locale, "btn_moderation", "menu:moderation")],
        [_btn(locale, "btn_economy", "menu:economy"), _btn(locale, "btn_games", "menu:games")],
        [_btn(locale, "btn_ratings", "menu:ratings"), _btn(locale, "btn_ai", "menu:ai")],
        [_btn(locale, "btn_stats", "menu:stats"), _btn(locale, "btn_settings", "menu:settings")],
        [_btn(locale, "btn_support", "menu:support")],
        [_btn(locale, "btn_close", "menu:close")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_keyboard(locale: str = "ru", target: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn(locale, "btn_back", target), _btn(locale, "btn_close", "menu:close")]]
    )


def menu_with_rows(locale: str, rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text=label, callback_data=data) for label, data in row]
        for row in rows
    ]
    keyboard.append([_btn(locale, "btn_back", "menu:main"), _btn(locale, "btn_close", "menu:close")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def toggle_row(locale: str, field: str, enabled: bool) -> list[tuple[str, str]]:
    mark = "✅" if enabled else "❌"
    label = {
        "antiflood_enabled": "Антифлуд",
        "antispam_enabled": "Антиспам",
        "antilink_enabled": "Антиссылки",
        "captcha_enabled": "CAPTCHA",
        "welcome_enabled": "Приветствие",
        "levels_enabled": "Уровни",
        "economy_enabled": "Экономика",
        "games_enabled": "Игры",
        "ai_enabled": "ИИ",
    }.get(field, field)
    return [(f"{mark} {label}", f"set:t:{field}")]


def confirm_keyboard(locale: str, yes_data: str, no_data: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=texts.t(locale, "btn_yes"), callback_data=yes_data),
                InlineKeyboardButton(text=texts.t(locale, "btn_no"), callback_data=no_data),
            ]
        ]
    )
