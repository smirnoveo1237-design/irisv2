"""Реестр команд IrisV2."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.commands.context import CommandContext

log = get_logger(__name__)

Handler = Callable[["CommandContext"], Awaitable[Any]]


@dataclass(slots=True)
class CommandSpec:
    name: str
    handler: Handler
    aliases: tuple[str, ...] = ()
    module: str = ""
    description_ru: str = ""
    description_en: str = ""
    usage: str = ""
    category: str = "general"
    admin: bool = False
    permission: str | None = None
    owner: bool = False
    group_only: bool = False
    private_only: bool = False
    allow_bare: bool = True
    cooldown: int = 0
    hidden: bool = False
    examples: tuple[str, ...] = field(default_factory=tuple)

    @property
    def all_names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


class CommandRegistry:
    def __init__(self) -> None:
        self._by_name: dict[str, CommandSpec] = {}
        self._by_alias: dict[str, CommandSpec] = {}

    def register(self, spec: CommandSpec) -> CommandSpec:
        previous = self._by_name.get(spec.name)
        if previous is not None:
            log.warning("Команда перерегистрирована", extra={"command": spec.name})
        self._by_name[spec.name] = spec
        for alias in spec.aliases:
            self._by_alias[alias] = spec
        return spec

    def get(self, name: str) -> CommandSpec | None:
        key = name.casefold()
        return self._by_name.get(key) or self._by_alias.get(key)

    def resolve(self, name: str) -> CommandSpec | None:
        return self.get(name)

    def known_names(self) -> set[str]:
        return set(self._by_name) | set(self._by_alias)

    def is_bare_allowed(self, name: str) -> bool:
        spec = self.get(name)
        return bool(spec and spec.allow_bare)

    def all(self) -> list[CommandSpec]:
        return sorted(self._by_name.values(), key=lambda item: (item.category, item.name))

    def by_category(self) -> dict[str, list[CommandSpec]]:
        result: dict[str, list[CommandSpec]] = {}
        for spec in self.all():
            result.setdefault(spec.category, []).append(spec)
        return result

    def __len__(self) -> int:
        return len(self._by_name)


registry = CommandRegistry()


def command(
    name: str,
    *,
    aliases: tuple[str, ...] = (),
    module: str = "",
    description_ru: str = "",
    description_en: str = "",
    usage: str = "",
    category: str = "general",
    admin: bool = False,
    permission: str | None = None,
    owner: bool = False,
    group_only: bool = False,
    private_only: bool = False,
    allow_bare: bool = True,
    cooldown: int = 0,
    hidden: bool = False,
    examples: tuple[str, ...] = (),
) -> Callable[[Handler], Handler]:
    """Декоратор регистрации обработчика команды.

    Обработчик получает :class:`CommandContext` и сам отвечает за ответ и права —
    но декларативные флаги (admin/owner/group_only/cooldown) проверяет диспетчер.
    """

    def decorator(func: Handler) -> Handler:
        registry.register(
            CommandSpec(
                name=name.casefold(),
                handler=func,
                aliases=tuple(alias.casefold() for alias in aliases),
                module=module or func.__module__.rsplit(".", 2)[-2],
                description_ru=description_ru,
                description_en=description_en,
                usage=usage,
                category=category,
                admin=admin,
                permission=permission,
                owner=owner,
                group_only=group_only,
                private_only=private_only,
                allow_bare=allow_bare,
                cooldown=cooldown,
                hidden=hidden,
                examples=examples,
            )
        )
        return func

    return decorator
