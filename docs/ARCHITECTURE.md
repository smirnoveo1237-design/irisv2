# Архитектура IrisV2

Документ описывает, из каких слоёв состоит бот, как проходит обработка сообщения и где
менять поведение. Он дополняет [README](../README.md) и [список команд](COMMANDS.md).

## 1. Слои

```
┌──────────────────────────────────────────────────────────────┐
│ Telegram (aiogram 3, long polling)                           │
├──────────────────────────────────────────────────────────────┤
│ Middleware                                                   │
│   ContainerMiddleware  — прокидывает зависимости             │
│   IrisMiddleware       — активность, антиспам, разбор команд │
├──────────────────────────────────────────────────────────────┤
│ commands/  parser → registry → router (права, кулдаун)       │
├──────────────────────────────────────────────────────────────┤
│ modules/   handlers.py (тонкие), service.py (логика)         │
├──────────────────────────────────────────────────────────────┤
│ services/  экономика, модерация, антиспам, уровни, ИИ, …     │
├──────────────────────────────────────────────────────────────┤
│ database/  SQLAlchemy 2 async + Alembic                      │
└──────────────────────────────────────────────────────────────┘
```

Правила зависимостей:

- `core` не знает о модулях;
- `services` знают о моделях и core, но не о Telegram-хендлерах (исключение —
  `services/moderation.py`, который вызывает Bot API, потому что это его предметная область);
- `modules` содержат обработчики и могут вызывать сервисы через `CommandContext`;
- `commands` не знают о конкретных модулях — только реестр и контекст.

## 2. Обработка сообщения

1. **ContainerMiddleware** кладёт `container` в `data`.
2. **IrisMiddleware** (только `message`):
   1. создаёт сессию БД и кладёт её в `data`;
   2. upsert `users`, `chats`, `chat_settings`, `chat_members`;
   3. обновляет `chat_stats`, `user_day_stats` и опыт (с кулдауном 60 с);
   4. проверяет антифлуд/антиспам/фильтры. При срабатывании — удаляет сообщение,
      применяет наказание, коммитит и **останавливает** обработку;
   5. разбирает команду через `parse_command` с префиксами и триггерами **этой группы**;
   6. если команда найдена — создаёт `CommandContext`, пишет аудит, вызвает следующий шаг.
3. **commands/executor.py** (вызывается из middleware для найденной команды):
   - `private_only` / `group_only` / `owner`;
   - `admin` или `permission` → `PermissionService.has_permission`;
   - модуль выключен в настройках группы → отказ;
   - кулдаун через кэш;
   - вызов `spec.handler(ctx)`; исключение → rollback + сообщение об ошибке.
4. Роутеры модулей обрабатывают колбэки, FSM, игры, ИИ и тикеты. «Мягкие» обработчики
   обязаны бросать `SkipHandler`, если событие не их, иначе следующие роутеры не получат его.
5. Middleware коммитит сессию и закрывает её.

## 3. Контекст команды

`CommandContext` — единственная точка доступа обработчика к окружению:

| Свойство | Назначение |
|---|---|
| `session` | AsyncSession на один апдейт |
| `user`, `chat_row`, `settings` | ORM-объекты, уже загруженные middleware |
| `chat_id`, `user_id`, `is_group`, `is_private` | Идентификаторы и тип чата |
| `args`, `args_text` | Разобранные аргументы и исходный остаток строки |
| `reply()`, `reply_plain()`, `delete_trigger()` | Ответы с обработкой ошибок Telegram |
| `economy`, `members`, `permissions`, `levels`, `moderation`, `analytics`, `tickets`, `ai` | Сервисы, созданные на текущую сессию |
| `resolve_target()` | Цель действия: reply → @username → ID |
| `t(key, **kwargs)` | Локализованный текст |

Права декларируются в `@command(...)`, а не проверяются вручную в каждом обработчике.

## 4. Реестр команд и разбор

`CommandSpec` содержит: имя, алиасы, модуль, категорию, описание RU/EN, usage, флаги
(`admin`, `permission`, `owner`, `group_only`, `private_only`, `allow_bare`), кулдаун.

`parse_command(text, known=..., config=...)`:

```
нормализация → снятие / | префикса | триггера → первое слово → проверка границы
→ проверка реестра → проверка allow_bare и длины → args
```

Ключевое свойство: разбор не ищет подстроки. `профилька`, `профильчик` и `антипрофиль`
не станут командой `профиль`, потому что сравнивается только первое слово целиком.

Префиксы и триггеры хранятся в `chat_settings` (JSON-массивы), поэтому меняются без рестарта:

```
chat_settings.command_prefixes = ["", "!", ".", "$"]
chat_settings.command_triggers = ["ирис", "iris"]
```

## 5. Данные

42 таблицы, сгруппированные по доменам:

| Домен | Таблицы |
|---|---|
| Пользователи и чаты | `users`, `chats`, `chat_settings`, `chat_members`, `chat_stats`, `user_day_stats` |
| Модерация | `warnings`, `moderation_logs`, `bans`, `filters`, `roles`, `user_roles` |
| Профили | `user_profiles`, `user_levels` (таблицы `achievements`/`user_achievements` остались в схеме как legacy и не используются) |
| Экономика | `wallets`, `transactions`, `shop_items`, `inventories` |
| Социальное | `friendships`, `families`, `family_members`, `marriages`, `pets`, `gifts`, `reputation_logs` |
| Игры | `quests`, `quest_progress`, `games` |
| Системное | `reports`, `automations`, `scheduled_tasks`, `ai_history`, `audit_logs`, `tickets`, `ticket_messages`, `giveaways`, `giveaway_members`, `polls`, `poll_votes`, `shipper_pairs` |

Инварианты:

- всё, что относится к группе, содержит `chat_id` и фильтруется по нему;
- `wallets` — уникальная пара `(chat_id, user_id)` + `CHECK (balance >= 0)`;
- `transactions.idempotency_key` уникален;
- `chat_members` — уникальная пара `(chat_id, user_id)`;
- денежные операции не используют `float`.

## 6. Экономика: почему не теряются Ириски

```python
# упрощённо
wallets = SELECT ... WHERE chat_id AND user_id IN (...) ORDER BY user_id FOR UPDATE
if sender.balance < amount: raise InsufficientFunds
sender.balance -= amount
receiver.balance += amount
INSERT INTO transactions (..., idempotency_key)
```

- Блокировка в порядке возрастания `user_id` исключает дедлоки между встречными переводами.
- Проверка баланса и списание происходят в одной транзакции.
- `CHECK (balance >= 0)` — последняя линия обороны.
- Повтор с тем же `idempotency_key` падает на уникальном индексе и превращается в
  `DuplicateOperation`, а не в двойное начисление.

## 7. Реестр участников

`chat_members` наполняется:

- любым сообщением пользователя (middleware);
- `new_chat_members` / `left_chat_member`;
- `get_chat_administrators` при вызове «шипперим»/«кто» и нехватке кандидатов;
- CAPTCHA подтверждает участие.

Полного списка участников Telegram не отдаёт, поэтому модули обязаны корректно работать
с неполным реестром: проверять количество кандидатов и объяснять ситуацию пользователю.

## 8. Как добавить модуль

1. Создать `app/modules/<name>/__init__.py` и `handlers.py` с `router = Router(...)`.
2. Описать команды:

   ```python
   @command("пример", aliases=("example",), module="<name>", category="general",
            description_ru="…", usage="пример", cooldown=3)
   async def example(ctx: CommandContext) -> None:
       await ctx.reply("Готово")
   ```

3. Добавить модуль в `MODULE_ORDER` в `app/modules/loader.py` (порядок = приоритет роутеров).
4. Написать тест в `tests/` (логику — в отдельный `service.py`, чтобы тестировать без Telegram).
5. Обновить `docs/COMMANDS.md`: `python scripts/dump_commands.py`.

## 9. Как добавить команду в существующий модуль

- Декоратор `@command(...)`; обработчик получает `CommandContext`.
- Права: `permission="ban"` или `admin=True`; владелец — `owner=True`.
- Ограничения: `group_only=True`, `private_only=True`, `allow_bare=False`.
- Не забыть `usage` и описания RU/EN — они попадают в `команды` и `docs/COMMANDS.md`.

## 10. Ошибки и наблюдаемость

- Любое исключение команды логируется с `command`, `chat_id`, `error`; сессия откатывается.
- Исключения в middleware не роняют polling: aiogram вызывает `on_error`, который логирует
  `update` и `exception`.
- `moderation_logs` и `audit_logs` — два независимых журнала: наказания и действия.
- В production включите `IRIS_LOG_JSON=true`, чтобы логи собирались структурно.

## 11. Тесты

- `tests/test_command_parser.py` — все формы вызова, границы, префиксы, лимиты.
- `tests/test_economy.py` — атомарность, идемпотентность, магазин, ежедневная награда.
- `tests/test_shipper.py`, `tests/test_iris_who.py` — уникальные команды без Telegram.
- `tests/test_antispam.py` — флуд, дубликаты, фишинг, капс, стоп-слова.
- `tests/test_dispatch.py` — полный путь `Update → middleware → команда` с подменой `Message.answer`.

Тестовая БД — SQLite в памяти со `StaticPool`; production — PostgreSQL. Диалект-зависимые
места (UPSERT, `FOR UPDATE`, `RETURNING`) инкапсулированы в сервисах и `database/utils.py`.
