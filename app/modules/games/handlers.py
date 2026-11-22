"""Игры: викторина, загадки, угадай число, КНБ, дуэли, квесты, турнир."""

from __future__ import annotations

import json
import random

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.commands.context import CommandContext
from app.commands.registry import command
from app.container import Container
from app.core.texts import texts
from app.core.timeutil import now_utc
from app.database.models import Game, User
from app.modules.common import mention
from app.modules.games.data import QUIZ, REWARDS, RIDDLES, RPS_LABELS, RPS_WINS
from app.services.economy import InsufficientFunds
from app.ui.keyboards import menu_with_rows
from app.ui.render import answer_alert, edit_or_send

router = Router(name="iris.games")

QUIZ_TTL = 300
RIDDLE_TTL = 300
GUESS_ATTEMPTS = 7


async def _reward(
    session, container: Container, chat_id: int, user_id: int, amount: int, xp: int, key: str
) -> None:
    if amount:
        try:
            await container.economy(session).credit(
                chat_id, user_id, amount, kind="game", reason="Игра", idempotency_key=key
            )
        except Exception:  # noqa: BLE001 - повторное начисление не критично
            pass
    if xp:
        await container.levels(session).award(chat_id, user_id, xp=xp)
        await container.quests(session).bump(chat_id, user_id, "xp", xp)


@command(
    "викторина",
    aliases=("quiz", "квиз"),
    module="games",
    category="games",
    description_ru="Вопрос викторины с вариантами ответа",
    description_en="Quiz question with options",
    usage="викторина",
    cooldown=5,
    group_only=True,
)
async def quiz(ctx: CommandContext) -> None:
    question_index = random.randrange(len(QUIZ))
    question = QUIZ[question_index]
    options = "\n".join(
        f"{index + 1}. {option}" for index, option in enumerate(question["options"])
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=str(index + 1),
                    callback_data=f"quiz:{question_index}:{index}",
                )
                for index in range(len(question["options"]))
            ]
        ]
    )
    sent = await ctx.message.answer(
        ctx.t("quiz_question", question=question["question"], options=options, seconds=QUIZ_TTL),
        reply_markup=keyboard,
    )
    if sent is not None:
        await ctx.container.cache.set(
            f"quiz:{ctx.chat_id}:{sent.message_id}",
            json.dumps({"correct": question["correct"], "answered": False}),
            ttl=QUIZ_TTL,
        )


@router.callback_query(F.data.startswith("quiz:"))
async def quiz_answer(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    try:
        _, raw_question, raw_option = callback.data.split(":")
        question = QUIZ[int(raw_question)]
        option = int(raw_option)
    except (ValueError, IndexError):
        await callback.answer()
        return

    key = f"quiz:{callback.message.chat.id}:{callback.message.message_id}"
    state_raw = await container.cache.get(key)
    if state_raw is None:
        await answer_alert(callback, "⌛ Время вышло или ответ уже дан.")
        return
    state = json.loads(state_raw)
    if state.get("answered"):
        await answer_alert(callback, "✅ На этот вопрос уже ответили.")
        return

    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, callback.message.chat.id)
        locale = container.locale(settings)
        if option == question["correct"]:
            state["answered"] = True
            await container.cache.set(key, json.dumps(state), ttl=QUIZ_TTL)
            await _reward(
                session,
                container,
                callback.message.chat.id,
                callback.from_user.id,
                REWARDS["quiz"],
                15,
                key,
            )
            text = texts.t(
                locale,
                "quiz_correct",
                user=mention(callback.from_user.id, callback.from_user.full_name),
                reward=REWARDS["quiz"],
                currency=texts.t(locale, "currency"),
            ) + f"\n\n❓ {question['question']}\n✅ {question['options'][question['correct']]}"
        else:
            text = texts.t(
                locale,
                "quiz_wrong",
                answer=question["options"][question["correct"]],
            )
    try:
        await callback.message.edit_text(text, reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    await callback.answer("✅" if option == question["correct"] else "❌")


@command(
    "загадка",
    aliases=("riddle",),
    module="games",
    category="games",
    description_ru="Загадка: ответьте сообщением в чат",
    description_en="Riddle: answer in chat",
    usage="загадка",
    cooldown=5,
    group_only=True,
)
async def riddle(ctx: CommandContext) -> None:
    item = random.choice(RIDDLES)
    await ctx.container.cache.set(
        f"riddle:{ctx.chat_id}",
        json.dumps({"answers": item["answers"], "reward": REWARDS["riddle"]}),
        ttl=RIDDLE_TTL,
    )
    await ctx.reply(
        ctx.t("riddle_question", question=item["question"])
        + "\n"
        + ctx.t("riddle_hint", hint=item["hint"]),
    )


@router.message(F.text.regexp(r"^[^/\s].{0,60}$"))
async def riddle_guess(message: Message, container: Container | None = None) -> None:
    if container is None or message.from_user is None:
        raise SkipHandler
    raw = await container.cache.get(f"riddle:{message.chat.id}")
    if raw is None:
        raise SkipHandler
    data = json.loads(raw)
    text = (message.text or "").strip().casefold()
    if not any(answer.casefold() in text for answer in data["answers"]):
        raise SkipHandler
    await container.cache.delete(f"riddle:{message.chat.id}")
    async with container.db.session_scope() as session:
        await _reward(
            session,
            container,
            message.chat.id,
            message.from_user.id,
            data["reward"],
            10,
            f"riddle:{message.chat.id}:{message.message_id}",
        )
        settings = await container.chats.settings(session, message.chat.id)
        locale = container.locale(settings)
        await message.answer(
            texts.t(
                locale,
                "quiz_correct",
                user=mention(message.from_user.id, message.from_user.full_name),
                reward=data["reward"],
                currency=texts.t(locale, "currency"),
            )
        )


@command(
    "угадай",
    aliases=("guess",),
    module="games",
    category="games",
    description_ru="Угадать число от 1 до 100",
    description_en="Guess a number 1–100",
    usage="угадай",
    cooldown=10,
    group_only=True,
)
async def guess(ctx: CommandContext) -> None:
    active = await ctx.session.scalar(
        select(Game).where(
            Game.chat_id == ctx.chat_id, Game.kind == "guess", Game.status == "active"
        )
    )
    if active is not None:
        await ctx.reply("🎲 Игра уже идёт — напишите число.")
        return
    number = random.randint(1, 100)
    game = Game(
        chat_id=ctx.chat_id,
        kind="guess",
        status="active",
        host_id=ctx.user_id,
        state={"number": number, "attempts": 0},
    )
    ctx.session.add(game)
    await ctx.session.flush()
    await ctx.reply(ctx.t("guess_started", attempts=GUESS_ATTEMPTS))


@router.message(F.text.regexp(r"^\s*\d{1,3}\s*$"))
async def guess_answer(message: Message, container: Container | None = None) -> None:
    if container is None or message.from_user is None:
        raise SkipHandler
    async with container.db.session_scope() as session:
        game = await session.scalar(
            select(Game).where(
                Game.chat_id == message.chat.id, Game.kind == "guess", Game.status == "active"
            )
        )
        if game is None:
            raise SkipHandler
        settings = await container.chats.settings(session, message.chat.id)
        locale = container.locale(settings)
        number = int(game.state.get("number", 0))
        guess_value = int((message.text or "0").strip())
        attempts = int(game.state.get("attempts", 0)) + 1
        game.state = {**game.state, "attempts": attempts}
        attempts_left = GUESS_ATTEMPTS - attempts

        if guess_value == number:
            game.status = "finished"
            game.winner_id = message.from_user.id
            game.finished_at = now_utc()
            await _reward(
                session,
                container,
                message.chat.id,
                message.from_user.id,
                REWARDS["guess"],
                20,
                f"guess:{game.id}",
            )
            await message.answer(
                texts.t(
                    locale,
                    "guess_win",
                    user=mention(message.from_user.id, message.from_user.full_name),
                    number=number,
                    reward=REWARDS["guess"],
                    currency=texts.t(locale, "currency"),
                )
            )
            return

        if attempts_left <= 0:
            game.status = "finished"
            game.finished_at = now_utc()
            await message.answer(texts.t(locale, "guess_lose", number=number))
            return

        key = "guess_higher" if guess_value < number else "guess_lower"
        await message.answer(texts.t(locale, key, attempts=attempts_left))


@command(
    "кнб",
    aliases=("rps", "камень"),
    module="games",
    category="games",
    description_ru="Камень, ножницы, бумага против IrisV2",
    description_en="Rock-paper-scissors vs IrisV2",
    usage="кнб",
    cooldown=3,
    group_only=True,
)
async def rps(ctx: CommandContext) -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=RPS_LABELS["rock"], callback_data=f"rps:rock:{ctx.user_id}"),
                InlineKeyboardButton(text=RPS_LABELS["paper"], callback_data=f"rps:paper:{ctx.user_id}"),
                InlineKeyboardButton(text=RPS_LABELS["scissors"], callback_data=f"rps:scissors:{ctx.user_id}"),
            ]
        ]
    )
    await ctx.reply(ctx.t("rps_choose"), keyboard=keyboard)


@router.callback_query(F.data.startswith("rps:"))
async def rps_answer(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    _, player_move, raw_user = callback.data.split(":")
    if callback.from_user.id != int(raw_user):
        await answer_alert(callback, "🙃 Это не ваша игра.")
        return
    bot_move = random.choice(list(RPS_WINS))
    if player_move == bot_move:
        result_key = "rps_draw"
        reward = 0
    elif RPS_WINS[player_move] == bot_move:
        result_key = "rps_win"
        reward = REWARDS["rps"]
    else:
        result_key = "rps_lose"
        reward = 0

    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, callback.message.chat.id)
        locale = container.locale(settings)
        if reward:
            await _reward(
                session,
                container,
                callback.message.chat.id,
                callback.from_user.id,
                reward,
                5,
                f"rps:{callback.message.message_id}",
            )
        outcome = texts.t(locale, result_key, reward=reward, currency=texts.t(locale, "currency"))
        text = texts.t(
            locale,
            "rps_result",
            user=mention(callback.from_user.id, callback.from_user.full_name),
            player=RPS_LABELS[player_move],
            bot=RPS_LABELS[bot_move],
            outcome=outcome,
        )
    await edit_or_send(callback, text, None)
    await callback.answer("🎉" if reward else "🤝")


@command(
    "дуэль",
    aliases=("duel",),
    module="games",
    category="games",
    description_ru="Вызвать участника на дуэль на Ириски",
    description_en="Challenge a member to a coin duel",
    usage="дуэль @user 50",
    cooldown=5,
    group_only=True,
)
async def duel(ctx: CommandContext) -> None:
    target = await ctx.resolve_target()
    if target is None or not target.user_id:
        await ctx.reply(ctx.t("no_target"))
        return
    if target.user_id == ctx.user_id:
        await ctx.reply(ctx.t("duel_self"))
        return
    raw_stake = ctx.arg(0) if ctx.message.reply_to_message else ctx.arg(1)
    stake = 0
    if raw_stake and raw_stake.isdigit():
        stake = max(0, min(int(raw_stake), 10000))
    if stake:
        balance = await ctx.economy.balance(ctx.chat_id, ctx.user_id)
        if balance < stake:
            await ctx.reply(ctx.t("duel_stake_bad"))
            return
    game = Game(
        chat_id=ctx.chat_id,
        kind="duel",
        status="pending",
        host_id=ctx.user_id,
        opponent_id=target.user_id,
        stake=stake,
        state={"challenger": ctx.user_id, "opponent": target.user_id, "stake": stake},
    )
    ctx.session.add(game)
    await ctx.session.flush()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚔️ Принять", callback_data=f"duel:a:{game.id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"duel:d:{game.id}"),
            ]
        ]
    )
    await ctx.reply(
        ctx.t(
            "duel_challenge",
            challenger=mention(ctx.user_id),
            opponent=mention(target.user_id, target.display),
            stake=stake,
            currency=ctx.t("currency"),
        ),
        keyboard=keyboard,
    )


@router.callback_query(F.data.startswith("duel:"))
async def duel_answer(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    _, action, raw_id = callback.data.split(":")
    async with container.db.session_scope() as session:
        game = await session.get(Game, int(raw_id))
        settings = await container.chats.settings(session, callback.message.chat.id)
        locale = container.locale(settings)
        if game is None or game.status != "pending":
            await answer_alert(callback, "⌛ Дуэль уже неактуальна.")
            return
        if game.opponent_id != callback.from_user.id:
            await answer_alert(callback, "🙃 Принять дуэль может только вызванный участник.")
            return
        if action == "d":
            game.status = "declined"
            game.finished_at = now_utc()
            await edit_or_send(callback, texts.t(locale, "duel_declined"), None)
            await callback.answer()
            return

        lock_key = f"duel_lock:{game.id}"
        if await container.cache.incr(lock_key, ttl=30) != 1:
            await answer_alert(callback, "⌛ Дуэль уже обрабатывается.")
            return

        stake = int(game.state.get("stake", 0))
        economy = container.economy(session)
        if stake:
            for uid in (game.host_id, game.opponent_id):
                if await economy.balance(callback.message.chat.id, uid) < stake:
                    await answer_alert(callback, texts.t(locale, "duel_stake_bad"))
                    return
            try:
                await economy.debit(
                    callback.message.chat.id, game.host_id, stake, kind="duel", reason=f"Дуэль #{game.id}"
                )
                await economy.debit(
                    callback.message.chat.id, game.opponent_id, stake, kind="duel", reason=f"Дуэль #{game.id}"
                )
            except InsufficientFunds:
                await answer_alert(callback, texts.t(locale, "duel_stake_bad"))
                return

        a_roll = random.randint(1, 6)
        b_roll = random.randint(1, 6)
        game.status = "finished"
        game.finished_at = now_utc()
        game.state = {**game.state, "a_roll": a_roll, "b_roll": b_roll}

        host = await session.get(User, game.host_id)
        opponent_name = callback.from_user.full_name
        text = texts.t(
            locale,
            "duel_accepted",
            a=mention(game.host_id, host.display_name if host else None),
            b=mention(game.opponent_id, opponent_name),
            a_roll=a_roll,
            b_roll=b_roll,
        )
        if a_roll == b_roll:
            if stake:
                await economy.credit(
                    callback.message.chat.id, game.host_id, stake, kind="duel_refund", reason="Ничья"
                )
                await economy.credit(
                    callback.message.chat.id, game.opponent_id, stake, kind="duel_refund", reason="Ничья"
                )
            text += "\n" + texts.t(locale, "duel_draw")
        else:
            winner = game.host_id if a_roll > b_roll else game.opponent_id
            game.winner_id = winner
            if stake:
                await economy.credit(
                    callback.message.chat.id,
                    winner,
                    stake * 2,
                    kind="duel_win",
                    reason=f"Дуэль #{game.id}",
                )
            text += "\n" + texts.t(
                locale,
                "duel_winner",
                user=mention(winner),
                amount=stake * 2,
                currency=texts.t(locale, "currency"),
            )
    await edit_or_send(callback, text, None)
    await callback.answer("⚔️")


@command(
    "квесты",
    aliases=("quests", "задания"),
    module="games",
    category="games",
    description_ru="Ежедневные задания и награды",
    description_en="Daily quests and rewards",
    usage="квесты",
    cooldown=3,
    group_only=True,
)
async def quests(ctx: CommandContext) -> None:
    service = ctx.container.quests(ctx.session)
    rewards = await service.claim(ctx.chat_id, ctx.user_id)
    progress = await service.progress_for(ctx.chat_id, ctx.user_id)
    lines = [ctx.t("quests_title"), ""]
    for quest, value, done in progress:
        status = "✅" if done else "⬜"
        lines.append(
            ctx.t(
                "quest_line",
                status=status,
                title=quest.title,
                progress=value,
                goal=quest.goal_value,
                reward=quest.reward_amount,
                xp=quest.reward_xp,
                currency=ctx.t("currency"),
            )
        )
    if rewards:
        total = sum(amount for _, amount in rewards)
        lines.append(f"\n🎁 Начислено: <b>+{total}</b> {ctx.t('currency')}")
    await ctx.reply("\n".join(lines))


@command(
    "турнир",
    aliases=("tournament", "топнедели"),
    module="games",
    category="games",
    description_ru="Турнир недели по опыту",
    description_en="Weekly XP tournament",
    usage="турнир",
    cooldown=5,
    group_only=True,
)
async def tournament(ctx: CommandContext) -> None:
    rows = await ctx.container.quests(ctx.session).week_top(ctx.chat_id, 10)
    if not rows:
        await ctx.reply(ctx.t("leaderboard_empty"))
        return
    lines = [ctx.t("tournament_title"), ""]
    for index, (user_id, xp, messages) in enumerate(rows, start=1):
        member = await ctx.members.get(ctx.chat_id, user_id)
        name = member.full_name if member else str(user_id)
        lines.append(
            f"{index}. {mention(user_id, name)} — <b>{xp}</b> XP · {messages} сообщений"
        )
    await ctx.reply("\n".join(lines))


@router.callback_query(F.data == "games:panel")
async def cb_panel(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None:
        await callback.answer()
        return
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, callback.message.chat.id)
        locale = container.locale(settings)
    await edit_or_send(
        callback,
        "🎮 <b>Развлечения</b>\n\n"
        "<code>викторина</code> · <code>загадка</code> · <code>угадай</code>\n"
        "<code>кнб</code> · <code>дуэль @user 50</code>\n"
        "<code>квесты</code> · <code>турнир</code>",
        menu_with_rows(locale, [[("🏆 Рейтинги", "menu:ratings")]]),
    )
    await callback.answer()


__all__ = ["router", "quiz", "riddle", "guess", "rps", "duel", "quests", "tournament", "GUESS_ATTEMPTS"]
