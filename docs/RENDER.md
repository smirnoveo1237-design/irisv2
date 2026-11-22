# Деплой IrisV2 на Render (бесплатный тариф)

Инструкция рассчитана на free web service Render: 512 МБ RAM, 0.1 CPU, 750 часов в месяц,
засыпание через 15 минут без входящего трафика и холодный старт около минуты.
Бот переведён в **webhook-режим**: Render принимает POST от Telegram на `/telegram/webhook`,
а `/health` используется health-check'ом.

Почему не long polling: free web service без входящего HTTP-трафика засыпает, а polling
не создаёт входящих запросов. Webhook, наоборот, будит сервис сообщением из Telegram.

## Что понадобится

| Компонент | Бесплатный вариант | Важно |
|---|---|---|
| Compute | Render Free Web Service | 512 МБ, 0.1 CPU, 750 ч/мес |
| База | **Neon Free Postgres** (рекомендуется) | Render Free Postgres удаляется через 30 дней |
| Кэш | встроенный `MemoryCache` | Redis не нужен, один инстанс |
| Файлы | нет | диск ephemeral: SQLite и локальные бэкапы не подходят |

Официальные ограничения Render: [Deploy for Free](https://render.com/docs/free),
[default env vars](https://render.com/docs/environment-variables).

## 1. База данных Neon

1. Создайте проект на [neon.tech](https://neon.tech), скопируйте connection string.
2. Для asyncpg нужен SSL. Можно вставить строку как есть — IrisV2 сам заменит
   `postgresql://` на `postgresql+asyncpg://` и `sslmode=` на `ssl=`:

   ```dotenv
   IRIS_DATABASE_URL=postgresql://user:password@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require
   ```

3. Миграции применит entrypoint контейнера: `alembic upgrade head`.

> Render Free Postgres живёт 30 дней и не имеет бэкапов. Для постоянного бота берите
> Neon/Supabase или платный Render Postgres.

## 2. Репозиторий

В Render Blueprint `render.yaml` должен лежать в корне репозитория. Загружайте **содержимое**
папки `IrisV2`, а не родительскую папку:

```powershell
cd C:\bot\Iris\IrisV2
git init
git add .
git commit -m "IrisV2 for Render"
git branch -M main
git remote add origin https://github.com/ВАШ_ЛОГИН/irisv2.git
git push -u origin main
```

Проверьте, что `.env` не попал в git:

```powershell
git status --short
git ls-files .env
```

Вторая команда должна ничего не вывести: `.env` уже в `.gitignore`.

## 3. Деплой через Blueprint

1. Render Dashboard → **New +** → **Blueprint**.
2. Подключите GitHub-репозиторий.
3. Render увидит `render.yaml`; нажмите **Apply**.
4. Заполните переменные, которые помечены `sync: false`:
   - `IRIS_BOT_TOKEN` — токен из @BotFather;
   - `IRIS_BOT_USERNAME` — username без `@`;
   - `IRIS_OWNER_IDS` — ваш Telegram ID;
   - `IRIS_SUPPORT_CHAT_ID` — ваш ID или чат поддержки (можно пусто);
   - `IRIS_DATABASE_URL` — строка Neon;
   - ключи ИИ (`GROQ_API_KEY`, `OPENROUTER_API_KEY`, `TOKENHARBOR_API_KEY`,
     `GEMINI_API_KEY`) — по желанию.
5. Deploy. Render соберёт Dockerfile и запустит entrypoint:
   ожидание БД → `alembic upgrade head` → `python -m app.main`.

`IRIS_WEBHOOK_ENABLED=true` и `IRIS_WEBHOOK_SECRET` (generateValue) уже заданы в
`render.yaml`. Публичный URL берётся из автоматической переменной Render
`RENDER_EXTERNAL_URL`; `IRIS_WEBHOOK_URL` нужен только для кастомного домена.

### Ключи и `.env`

Не коммитьте `.env` и API-ключи в GitHub: файл уже в `.gitignore`, а в `render.yaml`
секреты помечены `sync: false` и вводятся в Render Dashboard → **Environment**. Если ключи
уже попали в публичный репозиторий или чат — перевыпустите их у провайдера.

## 4. Проверка

Health-check:

```powershell
Invoke-WebRequest https://ИМЯ.onrender.com/health
# StatusCode: 200, Content: ok
```

Webhook в Telegram:

```powershell
$token = Read-Host "Bot token"
Invoke-RestMethod "https://api.telegram.org/bot$token/getWebhookInfo" | ConvertTo-Json -Depth 5
```

В ответе должно быть:

```json
{
  "url": "https://ИМЯ.onrender.com/telegram/webhook",
  "has_custom_certificate": false,
  "pending_update_count": 0
}
```

В логах Render:

```
Webhook установлен | url=https://.../telegram/webhook
HTTP-сервер запущен | port=...
```

Затем в группе: `ирис меню`, `профиль`, `.gpt привет`.

## 5. Переменные Render

Обязательные:

| Переменная | Пример | Зачем |
|---|---|---|
| `IRIS_BOT_TOKEN` | `123456:AA...` | токен бота |
| `IRIS_BOT_USERNAME` | `IrisV2Bot` | разбор `/cmd@bot` |
| `IRIS_OWNER_IDS` | `8502601092` | владелец бота |
| `IRIS_DATABASE_URL` | `postgresql://...neon.tech/neondb?sslmode=require` | PostgreSQL |
| `IRIS_WEBHOOK_ENABLED` | `true` | включает webhook |
| `IRIS_WEBHOOK_SECRET` | generateValue | проверка заголовка Telegram |

Оптимизация под free:

| Переменная | Значение | Почему |
|---|---|---|
| `IRIS_SCHEDULER_TICK` | `60` | реже опрос БД, меньше CPU |
| `IRIS_DB_POOL_SIZE` | `2` | 512 МБ RAM |
| `IRIS_DB_MAX_OVERFLOW` | `2` | не открывать лишние соединения |
| `IRIS_REDIS_URL` | пусто | MemoryCache на одном инстансе |
| `MALLOC_ARENA_MAX` | `2` | меньше RSS Python |
| `IRIS_LOG_JSON` | `true` | структурные логи Render |

## 6. Сон и холодный старт

Free web service засыпает через 15 минут без входящего трафика. Первое сообщение после сна
может ждать ~1 минуту: Render поднимает контейнер, приложение устанавливает webhook и
обрабатывает update. Telegram повторяет доставку, поэтому сообщение не теряется, но ответ
придёт с задержкой.

В проекте уже есть автопингер: `.github/workflows/keepalive.yml` каждые 10 минут дергает
`/health`. Это входящий HTTP-запрос для Render, поэтому сервис не засыпает. Ничего
дополнительно создавать не нужно, но workflow должен попасть в GitHub-репозиторий.

Если Render-сервис называется иначе, задайте Repository variable `RENDER_URL`:

```text
GitHub → Settings → Secrets and variables → Actions → Variables → New variable
RENDER_URL = https://ваш-сервис.onrender.com
```

Запустить пинг вручную: **Actions → Render keepalive → Run workflow**. Учтите: GitHub может
задерживать cron под нагрузкой, а в приватном репозитории минуты Actions расходуются из
квоты. При 10-минутном пинге сервис живёт 24/7 ≈ 730–744 ч в месяц при лимите Render 750 ч;
не пингуйте чаще 5 минут и не поднимайте второй бесплатный сервис.

## 7. Обновления

```powershell
git add .
git commit -m "update"
git push
```

Render пересоберёт и перезапустит сервис (autoDeploy). Миграции снова выполнит entrypoint.
Если меняли только переменные — **Manual Deploy → Deploy latest commit** или сохраните env:
Render перезапустит сервис.

## 8. Частые проблемы

| Симптом | Причина / решение |
|---|---|
| `502` / долгий первый ответ | сервис спал, идёт холодный старт; подождите ~1 мин |
| `Webhook включён, но нет публичного URL` | нет `RENDER_EXTERNAL_URL` и пуст `IRIS_WEBHOOK_URL`; задайте URL вручную |
| `getWebhookInfo` показывает старый URL | локальный polling ещё запущен или старый деплой; остановите его, перезапустите Render |
| `alembic: command not found` | сломан Docker build; смотрите Build logs |
| `password authentication failed` | неверный пароль/URL Neon; проверьте строку и SSL |
| `Free Postgres expired` | база Render живёт 30 дней; перейдите на Neon |
| Бот молчит в группе | privacy mode в BotFather или нет прав администратора |
| `no such table` | миграции не выполнились; смотрите логи entrypoint |
| Render suspended | исчерпаны 750 free hours или service-initiated traffic; проверьте Billing → Usage |

## 9. Что уже оптимизировано в коде

- webhook вместо polling, `handle_in_background=True` — Telegram получает быстрый 200;
- `/health` не обращается к БД;
- пул БД 2+2, `pool_recycle=300`, `pool_pre_ping`;
- планировщик раз в 60 секунд на Render;
- MemoryCache вместо Redis при одном инстансе;
- миграции в entrypoint, без ручных one-off jobs;
- JSON-логи и `MALLOC_ARENA_MAX=2`;
- никакого SQLite и локальных файлов на Render — только внешний Postgres.
