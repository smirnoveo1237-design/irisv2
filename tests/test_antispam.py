"""Тесты антиспама: капс, фишинг, флуд, дубликаты, стоп-слова."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.antispam import AntispamService, caps_ratio, looks_like_phishing, text_hash

CHAT_ID = -100900
USER_ID = 701


def make_message(text: str, user_id: int = USER_ID):
    return SimpleNamespace(
        message_id=1,
        text=text,
        caption=None,
        entities=[],
        chat=SimpleNamespace(id=CHAT_ID, type="supergroup", title="Spam test"),
        from_user=SimpleNamespace(
            id=user_id,
            is_bot=False,
            username="spammer",
            full_name="Spammer",
            first_name="Spammer",
            last_name=None,
        ),
    )


def test_caps_ratio() -> None:
    assert caps_ratio("привет") == 0
    assert caps_ratio("ПРИВЕТ МИР") > 0.9
    assert caps_ratio("ПрИвЕт МиР") < 0.9


def test_phishing_detection() -> None:
    assert looks_like_phishing("Срочно введите seed-фразу на https://wallet-check.top") is True
    assert looks_like_phishing("Купите скидку на https://shop.example.com") is False
    assert looks_like_phishing("Вот мой приватный ключ, заберите") is True


def test_text_hash_normalizes_spaces_and_case() -> None:
    assert text_hash("Привет   мир") == text_hash("привет мир")
    assert text_hash("привет") != text_hash("пока")


@pytest.mark.asyncio
async def test_antiflood(container) -> None:
    async with container.db.session_scope() as session:
        _, settings = await container.chats.ensure(
            session, chat_id=CHAT_ID, title="Spam", chat_type="supergroup"
        )
        settings.antiflood_enabled = True
        settings.flood_limit = 3
        settings.flood_window = 10
        service = AntispamService(container, session)
        verdicts = []
        for index in range(5):
            verdicts.append(
                await service.check(make_message(f"разное сообщение {index}"), settings)
            )
        assert verdicts[0] is None
        assert verdicts[2] is None
        assert verdicts[3] is not None and verdicts[3].reason == "flood"


@pytest.mark.asyncio
async def test_duplicate_messages(container) -> None:
    async with container.db.session_scope() as session:
        _, settings = await container.chats.ensure(
            session, chat_id=CHAT_ID, title="Spam", chat_type="supergroup"
        )
        settings.antiflood_enabled = False
        service = AntispamService(container, session)
        assert await service.check(make_message("одно и то же"), settings) is None
        verdict = await service.check(make_message("одно и то же"), settings)
        assert verdict is not None and verdict.reason == "duplicate"


@pytest.mark.asyncio
async def test_stop_words(container) -> None:
    async with container.db.session_scope() as session:
        _, settings = await container.chats.ensure(
            session, chat_id=CHAT_ID, title="Spam", chat_type="supergroup"
        )
        settings.antiflood_enabled = False
        settings.stop_words = ["реклама"]
        service = AntispamService(container, session)
        verdict = await service.check(make_message("Тут реклама магазина"), settings)
        assert verdict is not None and verdict.reason == "stop_word"


@pytest.mark.asyncio
async def test_caps_and_links(container) -> None:
    async with container.db.session_scope() as session:
        _, settings = await container.chats.ensure(
            session, chat_id=CHAT_ID, title="Spam", chat_type="supergroup"
        )
        settings.antiflood_enabled = False
        settings.anticaps_enabled = True
        settings.antilink_enabled = True
        service = AntispamService(container, session)
        assert (await service.check(make_message("ЭТО ОЧЕНЬ ГРОМКОЕ СООБЩЕНИЕ"), settings)).reason == "caps"
        assert (
            await service.check(make_message("смотри https://example.com/page"), settings)
        ).reason == "link"


@pytest.mark.asyncio
async def test_admins_are_ignored(container) -> None:
    async with container.db.session_scope() as session:
        _, settings = await container.chats.ensure(
            session, chat_id=CHAT_ID, title="Spam", chat_type="supergroup"
        )
        service = AntispamService(container, session)
        verdict = await service.check(make_message("а" * 100), settings, is_admin=True)
        assert verdict is None
