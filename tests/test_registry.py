"""Тесты реестра команд."""

from __future__ import annotations

from app.commands.registry import CommandRegistry, CommandSpec


async def _handler(ctx):  # pragma: no cover - заглушка
    return None


def build_registry() -> CommandRegistry:
    registry = CommandRegistry()
    registry.register(
        CommandSpec(name="профиль", handler=_handler, aliases=("profile",), module="profiles")
    )
    registry.register(
        CommandSpec(name="баланс", handler=_handler, aliases=("balance",), module="economy")
    )
    registry.register(
        CommandSpec(name="кто", handler=_handler, module="iris_who", allow_bare=False)
    )
    return registry


def test_resolve_by_name_and_alias() -> None:
    registry = build_registry()
    assert registry.get("профиль").name == "профиль"
    assert registry.get("profile").name == "профиль"
    assert registry.get("БАЛАНС").name == "баланс"
    assert registry.get("нет-такой") is None


def test_name_wins_over_alias() -> None:
    registry = CommandRegistry()
    first = CommandSpec(name="а", handler=_handler, aliases=("б",))
    second = CommandSpec(name="б", handler=_handler)
    registry.register(first)
    registry.register(second)
    assert registry.get("б").name == "б"
    assert registry.get("б").handler is second.handler


def test_bare_policy() -> None:
    registry = build_registry()
    assert registry.is_bare_allowed("профиль") is True
    assert registry.is_bare_allowed("кто") is False
    assert registry.is_bare_allowed("нет") is False


def test_categories_and_count() -> None:
    registry = build_registry()
    assert len(registry) == 3
    assert "профиль" in registry.known_names()
    assert "profile" in registry.known_names()
    assert len(registry.all()) == 3


def test_reregistration_keeps_single_entry() -> None:
    registry = CommandRegistry()
    registry.register(CommandSpec(name="x", handler=_handler, aliases=("y",)))
    registry.register(CommandSpec(name="x", handler=_handler, aliases=("y",)))
    assert len(registry) == 1
