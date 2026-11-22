"""Безопасное редактирование сообщений в колбэках."""

from __future__ import annotations

from aiogram.types import CallbackQuery, InlineKeyboardMarkup


async def edit_or_send(
    callback: CallbackQuery, text: str, keyboard: InlineKeyboardMarkup | None = None
) -> None:
    if callback.message is None:
        return
    try:
        await callback.message.edit_text(
            text, reply_markup=keyboard, disable_web_page_preview=True
        )
    except Exception:  # noqa: BLE001 - «message is not modified», права, старое сообщение
        try:
            await callback.message.answer(
                text, reply_markup=keyboard, disable_web_page_preview=True
            )
        except Exception:  # noqa: BLE001
            pass


async def answer_alert(callback: CallbackQuery, text: str) -> None:
    try:
        await callback.answer(text[:190], show_alert=True)
    except Exception:  # noqa: BLE001
        pass
