"""Тесты автоматизации: DSL и условия."""

from __future__ import annotations

from types import SimpleNamespace

from app.database.models import Automation
from app.services.automation import AutomationService


def make_message(text: str, user_id: int = 1):
    return SimpleNamespace(
        text=text,
        caption=None,
        chat=SimpleNamespace(id=-1, title="Auto"),
        from_user=SimpleNamespace(id=user_id, is_bot=False),
    )


def test_parse_rule_word_and_reply() -> None:
    parsed = AutomationService.parse_rule("слово=привет ответ=Здравствуйте, {user}!")
    assert parsed is not None
    conditions, actions = parsed
    assert conditions == {"word": "привет"}
    assert actions[0]["type"] == "reply"
    assert actions[0]["text"] == "Здравствуйте, {user}!"


def test_parse_rule_multiple_actions() -> None:
    parsed = AutomationService.parse_rule("слово=реклама удалить=1 мут=60 пред=1")
    assert parsed is not None
    _, actions = parsed
    assert [item["type"] for item in actions] == ["delete", "mute", "warn"]
    assert actions[1]["minutes"] == 60


def test_parse_rule_regex_and_reward() -> None:
    parsed = AutomationService.parse_rule(r"regex=спасибо|благодарю награда=15")
    assert parsed is not None
    conditions, actions = parsed
    assert conditions["regex"] == "спасибо|благодарю"
    assert actions[0]["type"] == "reward"
    assert actions[0]["amount"] == 15


def test_parse_rule_requires_action() -> None:
    assert AutomationService.parse_rule("слово=привет") is None
    assert AutomationService.parse_rule("просто текст") is None


def test_match_word_boundary() -> None:
    rule = Automation(conditions={"word": "привет"}, actions=[], chat_id=-1, name="r", event="message")
    assert AutomationService.match(rule, make_message("Привет, как дела"))
    assert not AutomationService.match(rule, make_message("приветствие"))


def test_match_conditions() -> None:
    rule = Automation(
        conditions={"contains": "ссылк", "min_len": 10},
        actions=[{"type": "delete"}],
        chat_id=-1,
        name="r",
        event="message",
    )
    assert AutomationService.match(rule, make_message("вот ссылка тут"))
    assert not AutomationService.match(rule, make_message("ссылка"))
    assert not AutomationService.match(rule, make_message("нет совпадения"))


def test_match_has_link() -> None:
    rule = Automation(
        conditions={"has_link": True}, actions=[{"type": "delete"}], chat_id=-1, name="r", event="message"
    )
    assert AutomationService.match(rule, make_message("смотри https://example.com"))
    assert not AutomationService.match(rule, make_message("без ссылки"))


def test_match_new_member_only() -> None:
    rule = Automation(
        conditions={"from_new": True}, actions=[{"type": "warn"}], chat_id=-1, name="r", event="message"
    )
    assert AutomationService.match(rule, make_message("первое сообщение"), is_new_member=True)
    assert not AutomationService.match(rule, make_message("старое"), is_new_member=False)
