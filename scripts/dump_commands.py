#!/usr/bin/env python
"""Генерирует docs/COMMANDS.md из реестра команд."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from app.commands.registry import registry
from app.modules.loader import discover_modules

CATEGORY_TITLES = {
    "general": "Общее",
    "moderation": "Модерация",
    "economy": "Экономика",
    "profiles": "Профили",
    "social": "Социальное",
    "games": "Игры",
    "fun": "Развлечения",
    "analytics": "Аналитика",
    "automation": "Автоматизация",
    "ai": "ИИ",
    "support": "Поддержка",
}

FLAGS = {
    "admin": "админ",
    "group_only": "только в группе",
    "private_only": "только в ЛС",
    "owner": "владелец бота",
    "allow_bare": "без префикса",
}


def main() -> int:
    for name in discover_modules():
        importlib.import_module(f"app.modules.{name}.handlers")

    lines = [
        "# Команды IrisV2",
        "",
        "Сгенерировано автоматически: `python scripts/dump_commands.py`.",
        "",
        "Любая команда работает в четырёх формах: `команда`, `!команда`, `.команда`, `ирис команда`.",
        "Стандартный `/команда` тоже поддерживается.",
        "",
    ]
    for category, specs in registry.by_category().items():
        lines.append(f"## {CATEGORY_TITLES.get(category, category)}")
        lines.append("")
        lines.append("| Команда | Алиасы | Описание | Использование | Ограничения |")
        lines.append("|---|---|---|---|---|")
        for spec in specs:
            if spec.hidden:
                continue
            flags = [
                label
                for attr, label in FLAGS.items()
                if getattr(spec, attr) and attr != "allow_bare"
            ]
            if spec.permission:
                flags.append(f"право: {spec.permission}")
            lines.append(
                "| `{name}` | {aliases} | {description} | `{usage}` | {flags} |".format(
                    name=spec.name,
                    aliases=", ".join(f"`{alias}`" for alias in spec.aliases) or "—",
                    description=spec.description_ru or "—",
                    usage=spec.usage or spec.name,
                    flags=", ".join(flags) or "—",
                )
            )
        lines.append("")

    target = Path("docs/COMMANDS.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8")
    print(f"Записано {target} ({len(registry)} команд)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
