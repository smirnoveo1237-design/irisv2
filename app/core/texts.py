"""Тексты интерфейса IrisV2 (RU/EN).

Все пользовательские строки собраны здесь, чтобы локализация была предсказуемой.
Ключи не переводятся: модули обращаются к ним по имени.
"""

from __future__ import annotations

import html

TEXTS: dict[str, tuple[str, str]] = {
    # --- Общее -------------------------------------------------------------
    "no_permission": (
        "⛔ Недостаточно прав для этого действия.",
        "⛔ You don't have permission to do that.",
    ),
    "owner_only": ("⛔ Команда доступна только владельцу бота.", "⛔ Bot owner only."),
    "group_only": ("👥 Команда работает только в группе.", "👥 This command works in groups only."),
    "private_only": ("💬 Команда работает только в личных сообщениях.", "💬 This command works in DM only."),
    "module_disabled": ("🔒 Модуль отключён в этой группе.", "🔒 This module is disabled in this chat."),
    "cooldown": ("⏳ Слишком часто. Подождите немного.", "⏳ Too fast, please wait."),
    "error": (
        "⚠️ Что-то пошло не так. Ошибка записана в журнал, попробуйте ещё раз.",
        "⚠️ Something went wrong. The error has been logged.",
    ),
    "not_enough_args": (
        "✍️ Не хватает аргументов. Пример: <code>{usage}</code>",
        "✍️ Missing arguments. Example: <code>{usage}</code>",
    ),
    "no_target": (
        "🎯 Не понял, к кому это относится. Ответьте на сообщение или укажите @username.",
        "🎯 Specify a target: reply to a message or mention @username.",
    ),
    "target_not_found": (
        "🔍 Не нашёл такого участника в реестре группы.",
        "🔍 Member not found in this chat registry.",
    ),
    "done": ("✅ Готово.", "✅ Done."),
    "cancelled": ("❌ Отменено.", "❌ Cancelled."),
    "unknown": ("🤔 Не понял команду.", "🤔 Unknown command."),
    "currency": ("Ириски", "Iris coins"),
    "you": ("вы", "you"),

    # --- Меню --------------------------------------------------------------
    "menu_title": (
        "🌸 <b>IrisV2</b> — экосистема вашего сообщества\n\n"
        "Модерация, профили, экономика, игры, аналитика и ИИ — в одном боте.\n"
        "Выберите раздел ниже или напишите команду: <code>ирис помощь</code>.",
        "🌸 <b>IrisV2</b> — your community ecosystem\n\n"
        "Moderation, profiles, economy, games, analytics and AI in one bot.\n"
        "Pick a section below or type <code>ирис помощь</code>.",
    ),
    "menu_hint": ("Раздел «{section}». Выберите действие.", "Section “{section}”. Choose an action."),
    "menu_private_note": (
        "ℹ️ Панель управления группой доступна в самой группе.",
        "ℹ️ The group control panel is available inside a group.",
    ),
    "btn_profile": ("👤 Профиль", "👤 Profile"),
    "btn_moderation": ("🛡️ Модерация", "🛡️ Moderation"),
    "btn_economy": ("💰 Экономика", "💰 Economy"),
    "btn_games": ("🎮 Развлечения", "🎮 Games"),
    "btn_ratings": ("🏆 Рейтинги", "🏆 Ratings"),
    "btn_ai": ("🤖 Ирис AI", "🤖 Iris AI"),
    "btn_stats": ("📊 Статистика", "📊 Statistics"),
    "btn_settings": ("⚙️ Настройки", "⚙️ Settings"),
    "btn_support": ("📩 Поддержка", "📩 Support"),
    "btn_back": ("⬅️ Назад", "⬅️ Back"),
    "btn_close": ("✖️ Закрыть", "✖️ Close"),
    "btn_yes": ("✅ Да", "✅ Yes"),
    "btn_no": ("❌ Нет", "❌ No"),
    "btn_confirm": ("✅ Подтвердить", "✅ Confirm"),
    "closed": ("Меню закрыто.", "Menu closed."),

    # --- Профиль -----------------------------------------------------------
    "profile_title": ("👤 <b>Профиль</b>", "👤 <b>Profile</b>"),
    "profile_body": (
        "{name}\n"
        "🆔 <code>{user_id}</code>\n"
        "📝 {bio}\n\n"
        "🏅 Уровень: <b>{level}</b> ({xp} XP)\n"
        "📈 До следующего уровня: <b>{xp_left}</b> XP\n"
        "💬 Сообщений в группе: <b>{messages}</b>\n"
        "💎 Репутация: <b>{reputation}</b>\n"
        "💰 Баланс: <b>{balance}</b> {currency}\n"
        "{vip}{marriage}"
        "\n<i>Профиль обновлён {updated}</i>",
        "{name}\n"
        "🆔 <code>{user_id}</code>\n"
        "📝 {bio}\n\n"
        "🏅 Level: <b>{level}</b> ({xp} XP)\n"
        "📈 XP to next level: <b>{xp_left}</b>\n"
        "💬 Messages in chat: <b>{messages}</b>\n"
        "💎 Reputation: <b>{reputation}</b>\n"
        "💰 Balance: <b>{balance}</b> {currency}\n"
        "{vip}{marriage}"
        "\n<i>Updated {updated}</i>",
    ),
    "profile_vip": ("⭐ VIP до {date}\n", "⭐ VIP until {date}\n"),
    "profile_married": (
        "💍 В браке с {partner} · {date}\n",
        "💍 Married to {partner} · {date}\n",
    ),
    "profile_no_partner": (
        "💔 Свободен(а). Предложить брак: <code>ирис брак @user</code>",
        "💔 Single. Propose: <code>iris marry @user</code>",
    ),
    "profile_no_bio": ("Описание не задано — <code>ирис био текст</code>", "No bio yet — try <code>iris bio text</code>"),
    "profile_bio_set": ("✅ Описание профиля обновлено.", "✅ Profile bio updated."),
    "profile_bio_too_long": (
        "✍️ Описание слишком длинное (максимум {limit} символов).",
        "✍️ Bio is too long (max {limit} characters).",
    ),
    "level_up": (
        "🎉 {name} достиг <b>{level}</b> уровня!",
        "🎉 {name} reached level <b>{level}</b>!",
    ),
    # --- Экономика ---------------------------------------------------------
    "economy_disabled": ("💰 Экономика отключена в этой группе.", "💰 Economy is disabled here."),
    "balance": (
        "💰 <b>{name}</b>, на вашем счету <b>{balance}</b> {currency}.\n"
        "📊 Всего заработано: {earned} · потрачено: {spent}",
        "💰 <b>{name}</b>, your balance is <b>{balance}</b> {currency}.\n"
        "📊 Earned: {earned} · spent: {spent}",
    ),
    "wallet_created": (
        "💰 Кошелёк создан. Стартовый бонус: <b>{amount}</b> {currency}.",
        "💰 Wallet created. Welcome bonus: <b>{amount}</b> {currency}.",
    ),
    "transfer_ok": (
        "💸 Перевод выполнен: <b>{amount}</b> {currency} → {target}.\n"
        "Ваш баланс: <b>{balance}</b> {currency}.",
        "💸 Sent <b>{amount}</b> {currency} to {target}.\nYour balance: <b>{balance}</b> {currency}.",
    ),
    "transfer_received": (
        "💸 {sender} перевёл вам <b>{amount}</b> {currency}.",
        "💸 {sender} sent you <b>{amount}</b> {currency}.",
    ),
    "transfer_bad_amount": (
        "🔢 Укажите сумму больше нуля: <code>{usage}</code>",
        "🔢 Amount must be positive: <code>{usage}</code>",
    ),
    "insufficient_funds": (
        "💸 Недостаточно {currency}: нужно <b>{need}</b>, на счету <b>{have}</b>.",
        "💸 Not enough {currency}: need <b>{need}</b>, you have <b>{have}</b>.",
    ),
    "transfer_self": ("🙃 Нельзя перевести самому себе.", "🙃 You can't transfer to yourself."),
    "daily_ok": (
        "🎁 Ежедневная награда: <b>+{amount}</b> {currency}.\n"
        "🔥 Серия: <b>{streak}</b> дн. · Баланс: <b>{balance}</b>",
        "🎁 Daily reward: <b>+{amount}</b> {currency}.\n"
        "🔥 Streak: <b>{streak}</b> days · Balance: <b>{balance}</b>",
    ),
    "daily_already": (
        "⏳ Награда уже получена. Следующая — через {hours} ч.",
        "⏳ Already claimed. Next reward in {hours} h.",
    ),
    "shop_title": ("🛍️ <b>Магазин</b> · {currency}", "🛍️ <b>Shop</b> · {currency}"),
    "shop_empty": ("🛍️ Магазин пока пуст.", "🛍️ The shop is empty."),
    "shop_bought": (
        "🛍️ Куплено: <b>{title}</b> за <b>{price}</b> {currency}.\nБаланс: <b>{balance}</b>",
        "🛍️ Purchased <b>{title}</b> for <b>{price}</b> {currency}.\nBalance: <b>{balance}</b>",
    ),
    "shop_no_item": ("🛍️ Товар не найден.", "🛍️ Item not found."),
    "shop_no_stock": ("📦 Этот товар закончился.", "📦 Out of stock."),
    "inventory_title": ("🎒 <b>Инвентарь</b>", "🎒 <b>Inventory</b>"),
    "inventory_empty": ("🎒 Инвентарь пуст. Загляните в магазин: <code>ирис магазин</code>", "🎒 Inventory is empty. Try <code>iris shop</code>"),
    "history_title": ("🧾 <b>История операций</b>", "🧾 <b>Transaction history</b>"),
    "history_empty": ("🧾 Операций пока нет.", "🧾 No transactions yet."),
    "top_balance": ("💰 <b>Богачи группы</b>", "💰 <b>Richest members</b>"),

    # --- Модерация ---------------------------------------------------------
    "mod_title": ("🛡️ <b>Модерация</b>", "🛡️ <b>Moderation</b>"),
    "mod_panel_body": (
        "Выберите действие. Все наказания попадают в журнал и историю участника.",
        "Pick an action. Every punishment is written to the log and user history.",
    ),
    "mod_banned": (
        "🔨 {target} забанен.\n👮 Модератор: {moderator}\n📝 Причина: {reason}{until}",
        "🔨 {target} was banned.\n👮 Moderator: {moderator}\n📝 Reason: {reason}{until}",
    ),
    "mod_unbanned": ("✅ {target} разбанен.", "✅ {target} was unbanned."),
    "mod_muted": (
        "🔇 {target} получил мут на {duration}.\n📝 Причина: {reason}",
        "🔇 {target} muted for {duration}.\n📝 Reason: {reason}",
    ),
    "mod_unmuted": ("🔊 {target} размучен.", "🔊 {target} was unmuted."),
    "mod_kicked": ("👢 {target} исключён из группы.", "👢 {target} was kicked."),
    "mod_warned": (
        "⚠️ {target} получил предупреждение ({count}/{limit}).\n📝 Причина: {reason}",
        "⚠️ {target} warned ({count}/{limit}).\n📝 Reason: {reason}",
    ),
    "mod_warn_auto": (
        "🚷 Лимит предупреждений исчерпан — применено: <b>{action}</b>.",
        "🚷 Warning limit reached — applied: <b>{action}</b>.",
    ),
    "mod_warns_cleared": ("🧹 Предупреждения {target} сняты.", "🧹 Warnings for {target} cleared."),
    "mod_warns_list": ("⚠️ <b>Предупреждения {target}</b>\n{items}", "⚠️ <b>Warnings of {target}</b>\n{items}"),
    "mod_no_warns": ("✨ У {target} нет активных предупреждений.", "✨ {target} has no active warnings."),
    "mod_deleted": ("🧹 Удалено сообщений: <b>{count}</b>.", "🧹 Deleted messages: <b>{count}</b>."),
    "mod_no_rights": (
        "🚫 У IrisV2 нет прав на это действие. Выдайте боту права администратора "
        "(бан/ограничение участников, удаление сообщений).",
        "🚫 IrisV2 lacks permissions. Grant the bot admin rights (restrict members, delete messages).",
    ),
    "mod_self": ("🙃 Нельзя применить наказание к самому себе.", "🙃 You can't punish yourself."),
    "mod_admin_target": ("👑 Нельзя наказать администратора группы.", "👑 You can't punish a chat admin."),
    "mod_bot_target": ("🤖 Нельзя наказать бота.", "🤖 You can't punish a bot."),
    "mod_history_title": ("📜 <b>История наказаний</b>", "📜 <b>Punishment history</b>"),
    "mod_history_empty": ("📜 История пуста.", "📜 No records."),
    "mod_duration_bad": (
        "⏱️ Не понял срок. Примеры: <code>10м</code>, <code>2ч</code>, <code>1д</code>, <code>7д</code>.",
        "⏱️ Unknown duration. Examples: <code>10m</code>, <code>2h</code>, <code>1d</code>.",
    ),
    "mod_log": (
        "🛡️ <b>{action}</b>\n👤 Участник: {target}\n👮 Модератор: {moderator}\n📝 Причина: {reason}",
        "🛡️ <b>{action}</b>\n👤 Member: {target}\n👮 Moderator: {moderator}\n📝 Reason: {reason}",
    ),

    # --- Шипперим / кто ----------------------------------------------------
    "ship_title": ("💘 <b>Шипперим</b>", "💘 <b>Shipping</b>"),
    "ship_result": (
        "💘 <b>Шипперим</b>\n\n{first}  ✨  {second}\n\n"
        "Совместимость: <b>{score}%</b>\n{bar}\n\n<i>{phrase}</i>",
        "💘 <b>Shipping</b>\n\n{first}  ✨  {second}\n\n"
        "Compatibility: <b>{score}%</b>\n{bar}\n\n<i>{phrase}</i>",
    ),
    "ship_not_enough": (
        "💘 Для шипперим нужно минимум два участника.\n"
        "Позовите людей в группу или подождите, пока реестр участников наполнится.",
        "💘 Shipping needs at least two members.\nInvite people or wait until the member registry fills up.",
    ),
    "ship_no_repeat": (
        "💘 Все пары из недавней истории уже показаны — начнём новый круг!",
        "💘 All recent pairs were already shown — starting a new round!",
    ),
    "who_title": ("🔮 <b>Ирис кто</b>", "🔮 <b>Iris who</b>"),
    "who_not_enough": (
        "🔮 В группе пока нет участников в реестре. Напишите что-нибудь — и я запомню.",
        "🔮 No members in the registry yet. Say something and I'll remember you.",
    ),
    "who_answer": ("🔮 {user} — {text}", "🔮 {user} — {text}"),
    "who_no_text": ("загадочная личность", "a mysterious person"),

    # --- Игры --------------------------------------------------------------
    "games_title": ("🎮 <b>Развлечения</b>", "🎮 <b>Games</b>"),
    "quiz_question": (
        "❓ <b>Викторина</b>\n\n{question}\n\n{options}\n\n<i>Ответьте номером варианта в течение {seconds} сек.</i>",
        "❓ <b>Quiz</b>\n\n{question}\n\n{options}\n\n<i>Reply with the option number within {seconds}s.</i>",
    ),
    "quiz_correct": ("✅ Верно! {user} получает <b>+{reward}</b> {currency}.", "✅ Correct! {user} gets <b>+{reward}</b> {currency}."),
    "quiz_wrong": ("❌ Неверно. Правильный ответ: <b>{answer}</b>.", "❌ Wrong. Correct answer: <b>{answer}</b>."),
    "riddle_question": ("🧩 <b>Загадка</b>\n\n{question}", "🧩 <b>Riddle</b>\n\n{question}"),
    "riddle_hint": ("💡 Подсказка: {hint}", "💡 Hint: {hint}"),
    "guess_started": (
        "🎲 Я загадал число от <b>1</b> до <b>100</b>. У вас {attempts} попыток — просто напишите число.",
        "🎲 I picked a number from <b>1</b> to <b>100</b>. You have {attempts} attempts — just type a number.",
    ),
    "guess_higher": ("📈 Больше! Осталось попыток: {attempts}", "📈 Higher! Attempts left: {attempts}"),
    "guess_lower": ("📉 Меньше! Осталось попыток: {attempts}", "📉 Lower! Attempts left: {attempts}"),
    "guess_win": ("🎉 {user} угадал число <b>{number}</b> и получает <b>+{reward}</b> {currency}!", "🎉 {user} guessed <b>{number}</b> and gets <b>+{reward}</b> {currency}!"),
    "guess_lose": ("😔 Попытки закончились. Было загадано <b>{number}</b>.", "😔 Out of attempts. The number was <b>{number}</b>."),
    "rps_choose": ("✊✋✌️ <b>Камень, ножницы, бумага</b>\nВыберите свой ход:", "✊✋✌️ <b>Rock, paper, scissors</b>\nPick your move:"),
    "rps_result": (
        "{user}: {player} · IrisV2: {bot}\n\n{outcome}",
        "{user}: {player} · IrisV2: {bot}\n\n{outcome}",
    ),
    "rps_win": ("🎉 Победа! +{reward} {currency}", "🎉 You win! +{reward} {currency}"),
    "rps_lose": ("😔 Проигрыш. В следующий раз повезёт!", "😔 You lose. Better luck next time!"),
    "rps_draw": ("🤝 Ничья.", "🤝 Draw."),
    "duel_challenge": (
        "⚔️ {challenger} вызывает {opponent} на дуэль!\nСтавка: <b>{stake}</b> {currency}.\n\n{opponent}, принимаете?",
        "⚔️ {challenger} challenges {opponent}!\nStake: <b>{stake}</b> {currency}.\n\n{opponent}, accept?",
    ),
    "duel_accepted": ("⚔️ Дуэль принята! {a} выбросил {a_roll}, {b} — {b_roll}.", "⚔️ Duel accepted! {a} rolled {a_roll}, {b} rolled {b_roll}."),
    "duel_winner": ("🏆 Победитель: {user} (+{amount} {currency})", "🏆 Winner: {user} (+{amount} {currency})"),
    "duel_draw": ("🤝 Ничья — ставки возвращены.", "🤝 Draw — stakes returned."),
    "duel_declined": ("❌ Дуэль отклонена.", "❌ Duel declined."),
    "duel_self": ("🙃 Нельзя вызвать самого себя.", "🙃 You can't challenge yourself."),
    "duel_stake_bad": ("💰 Недостаточно средств для ставки.", "💰 Not enough funds for the stake."),
    "quests_title": ("📜 <b>Ежедневные задания</b>", "📜 <b>Daily quests</b>"),
    "quest_line": ("{status} <b>{title}</b> — {progress}/{goal}\n   🎁 {reward} {currency} · {xp} XP"),
    "quests_done": ("🎉 Все задания на сегодня выполнены!", "🎉 All quests for today are done!"),
    "tournament_title": ("🏆 <b>Турнир недели</b> по опыту", "🏆 <b>Weekly tournament</b> by XP"),
    "leaderboard_title": ("🏆 <b>Рейтинг</b>", "🏆 <b>Leaderboard</b>"),
    "leaderboard_empty": ("Пока пусто — станьте первым!", "Empty for now — be the first!"),

    # --- Социальное --------------------------------------------------------
    "social_title": ("💞 <b>Социальные связи</b>", "💞 <b>Social</b>"),
    "friend_request_sent": ("🤝 Заявка в друзья отправлена {target}.", "🤝 Friend request sent to {target}."),
    "friend_request_incoming": ("🤝 {name} хочет добавить вас в друзья.", "🤝 {name} wants to add you as a friend."),
    "friend_accepted": ("✅ {name} теперь ваш друг.", "✅ {name} is now your friend."),
    "friend_declined": ("❌ Заявка отклонена.", "❌ Request declined."),
    "friend_exists": ("🤝 Вы уже друзья.", "🤝 You are already friends."),
    "friend_self": ("🙃 С собой дружить неинтересно.", "🙃 You can't befriend yourself."),
    "friends_list": ("🤝 <b>Друзья</b>\n{items}", "🤝 <b>Friends</b>\n{items}"),
    "friends_empty": ("🤝 Пока нет друзей. Начните с <code>ирис друг @username</code>", "🤝 No friends yet. Try <code>iris friend @username</code>"),
    "marriage_proposed": ("💍 {name} предлагает вам брак! Принять?", "💍 {name} proposes to you! Accept?"),
    "marriage_created": ("💍 {a} и {b} теперь семья! Горько! 🥂", "💍 {a} and {b} are married! 🥂"),
    "marriage_exists": ("💍 Один из вас уже состоит в браке.", "💍 One of you is already married."),
    "marriage_none": ("💔 Вы не состоите в браке.", "💔 You are not married."),
    "marriage_divorced": ("💔 Брак расторгнут.", "💔 Divorced."),
    "family_created": ("👨‍👩‍👧 Семья <b>{name}</b> создана! Вступить: <code>ирис семья вступить {name}</code>", "👨‍👩‍👧 Family <b>{name}</b> created! Join: <code>iris family join {name}</code>"),
    "family_exists": ("👨‍👩‍👧 Семья с таким названием уже есть.", "👨‍👩‍👧 This family name is taken."),
    "family_joined": ("✅ Вы вступили в семью <b>{name}</b>.", "✅ You joined the family <b>{name}</b>."),
    "family_not_found": ("🔍 Семья не найдена.", "🔍 Family not found."),
    "family_in_other": ("👨‍👩‍👧 Вы уже состоите в другой семье.", "👨‍👩‍👧 You are already in a family."),
    "family_info": (
        "👨‍👩‍👧 <b>{name}</b>\n👑 Глава: {owner}\n👥 Участников: {count}\n📝 {description}\n\n{members}",
        "👨‍👩‍👧 <b>{name}</b>\n👑 Owner: {owner}\n👥 Members: {count}\n📝 {description}\n\n{members}",
    ),
    "pet_none": ("🐾 У вас нет питомца. Купить: <code>ирис питомец купить кот</code>", "🐾 No pet yet. Buy one: <code>iris pet buy cat</code>"),
    "pet_adopted": ("🐾 {name} теперь ваш питомец!", "🐾 {name} is now your pet!"),
    "pet_info": ("{emoji} <b>{name}</b> ({species})\nУровень: {level} · Сытость: {hunger}% · Настроение: {happiness}%", "{emoji} <b>{name}</b> ({species})\nLevel: {level} · Hunger: {hunger}% · Mood: {happiness}%"),
    "pet_fed": ("🍖 {name} покормлен. Сытость: {hunger}%", "🍖 {name} has been fed. Hunger: {hunger}%"),
    "pet_no_money": ("💰 Корм стоит {price} {currency}, у вас {balance}.", "💰 Food costs {price} {currency}, you have {balance}."),
    "gift_sent": ("🎁 Подарок для {target}: {text}", "🎁 Gift for {target}: {text}"),
    "gift_no_item": ("🎁 У вас нет такого предмета в инвентаре.", "🎁 You don't have this item."),
    "reputation_given": ("💎 Вы повысили репутацию {target} до {value}.", "💎 You raised {target}'s reputation to {value}."),
    "reputation_self": ("🙃 Свою репутацию повышать нельзя.", "🙃 You can't boost your own reputation."),
    "reputation_cooldown": ("⏳ Репутацию можно повышать раз в 24 часа.", "⏳ Reputation can be given once per 24 hours."),

    # --- Аналитика ---------------------------------------------------------
    "stats_title": ("📊 <b>Статистика группы</b>", "📊 <b>Chat statistics</b>"),
    "stats_body": (
        "👥 Участников в реестре: <b>{members}</b>\n"
        "💬 Сообщений сегодня: <b>{messages_today}</b>\n"
        "🗓️ Сообщений за 7 дней: <b>{messages_week}</b>\n"
        "👋 Пришло за неделю: <b>{joins}</b> · ушло: <b>{leaves}</b>\n"
        "🛡️ Наказаний за неделю: <b>{moderated}</b>\n"
        "💰 Ирисок в обороте: <b>{economy}</b>\n"
        "🏆 Самый активный: {top_user}",
        "👥 Members in registry: <b>{members}</b>\n"
        "💬 Messages today: <b>{messages_today}</b>\n"
        "🗓️ Messages in 7 days: <b>{messages_week}</b>\n"
        "👋 Joined: <b>{joins}</b> · left: <b>{leaves}</b>\n"
        "🛡️ Punishments: <b>{moderated}</b>\n"
        "💰 Coins in circulation: <b>{economy}</b>\n"
        "🏆 Most active: {top_user}",
    ),
    "stats_no_data": ("📊 Данных пока нет — нужно несколько сообщений.", "📊 No data yet — messages needed."),

    # --- Настройки ---------------------------------------------------------
    "settings_title": ("⚙️ <b>Настройки IrisV2</b>", "⚙️ <b>IrisV2 settings</b>"),
    "settings_body": (
        "🛡️ Антифлуд: {antiflood} · Антиспам: {antispam} · Антиссылки: {antilink}\n"
        "🔐 CAPTCHA: {captcha} · Приветствие: {welcome}\n"
        "📈 Уровни: {levels} · 💰 Экономика: {economy} · 🎮 Игры: {games}\n"
        "🤖 ИИ: {ai} · 🌐 Язык: {lang}\n\n"
        "⌨️ Префиксы команд: <code>{prefixes}</code>\n"
        "Триггеры: <code>{triggers}</code>\n"
        "⚠️ Лимит предупреждений: {max_warnings} · мут по умолчанию: {mute} мин.",
        "🛡️ Antiflood: {antiflood} · Antispam: {antispam} · Antilink: {antilink}\n"
        "🔐 CAPTCHA: {captcha} · Welcome: {welcome}\n"
        "📈 Levels: {levels} · 💰 Economy: {economy} · 🎮 Games: {games}\n"
        "🤖 AI: {ai} · 🌐 Locale: {lang}\n\n"
        "⌨️ Command prefixes: <code>{prefixes}</code>\n"
        "Triggers: <code>{triggers}</code>\n"
        "⚠️ Warning limit: {max_warnings} · default mute: {mute} min.",
    ),
    "settings_saved": ("✅ Настройка обновлена.", "✅ Setting updated."),
    "settings_ship_cooldown": (
        "💘 Задержка «Шипперим»: <b>{seconds}</b> с · изменить: <code>шипперим задержка 60</code>",
        "💘 Ship cooldown: <b>{seconds}</b> s · change: <code>ship cooldown 60</code>",
    ),
    "settings_welcome_set": ("✅ Текст приветствия обновлён.", "✅ Welcome text updated."),
    "settings_prefix_set": (
        "✅ Префиксы обновлены: <code>{prefixes}</code>",
        "✅ Prefixes updated: <code>{prefixes}</code>",
    ),
    "settings_prefix_bad": (
        "⌨️ Укажите префиксы через пробел. Пример: <code>ирис префиксы ! . $</code>",
        "⌨️ Provide prefixes separated by spaces, e.g. <code>iris prefixes ! . $</code>",
    ),
    "settings_locale_set": ("✅ Язык группы: {lang}.", "✅ Chat locale: {lang}."),
    "settings_welcome_help": (
        "✍️ Отправьте новый текст приветствия. Доступно: {user}, {chat}, {count}.\n/cancel — отмена.",
        "✍️ Send the new welcome text. Variables: {user}, {chat}, {count}.\n/cancel to cancel.",
    ),
    "settings_ai_no_key": (
        "🤖 ИИ отключён на уровне сервера: не задан IRIS_AI_API_KEY.",
        "🤖 AI is disabled server-side: IRIS_AI_API_KEY is missing.",
    ),

    # --- ИИ ----------------------------------------------------------------
    "ai_title": ("🤖 <b>Ирис AI</b>", "🤖 <b>Iris AI</b>"),
    "ai_hint": (
        "Напишите вопрос: <code>ирис ии как настроить капчу?</code>\n\n"
        "Я помогу с командами, настройками, приветствиями и кратким изложением обсуждения. "
        "Административные действия без вашего подтверждения я не выполняю.",
        "Ask me anything: <code>iris ai how do I enable captcha?</code>\n\n"
        "I can explain commands, settings, write greetings and summarise discussions. "
        "I never perform admin actions without your confirmation.",
    ),
    "ai_thinking": ("🤖 Думаю…", "🤖 Thinking…"),
    "ai_unavailable": (
        "🤖 ИИ сейчас недоступен. Проверьте IRIS_AI_API_KEY и IRIS_AI_BASE_URL.",
        "🤖 AI is unavailable. Check IRIS_AI_API_KEY and IRIS_AI_BASE_URL.",
    ),
    "ai_error": ("🤖 Не удалось получить ответ: {error}", "🤖 AI error: {error}"),
    "ai_disabled": ("🤖 ИИ отключён в этой группе: <code>ирис настройки</code>", "🤖 AI is disabled here: <code>iris settings</code>"),
    "ai_summary_empty": ("🤖 Недостаточно сообщений для изложения.", "🤖 Not enough messages to summarise."),
    "ai_summary_title": ("🤖 <b>Краткое изложение обсуждения</b>\n\n{text}", "🤖 <b>Discussion summary</b>\n\n{text}"),
    "ai_explain": ("🤖 <b>{command}</b>\n\n{text}", "🤖 <b>{command}</b>\n\n{text}"),
    "ai_greeting": ("🤖 Вариант приветствия:\n\n{text}", "🤖 Welcome variant:\n\n{text}"),
    "ai_too_long": ("✍️ Слишком длинный запрос (максимум {limit} символов).", "✍️ Request is too long (max {limit} chars)."),

    # --- Поддержка и жалобы ------------------------------------------------
    "support_title": ("📩 <b>Поддержка IrisV2</b>", "📩 <b>IrisV2 support</b>"),
    "support_hint": (
        "Опишите проблему: <code>ирис поддержка не работает капча</code>\n"
        "Тикет увидит команда поддержки. Ответ придёт сюда.",
        "Describe your issue: <code>iris support captcha is broken</code>\n"
        "Our team will see the ticket and reply here.",
    ),
    "support_created": ("📩 Тикет <b>#{ticket_id}</b> создан. Мы ответим здесь.", "📩 Ticket <b>#{ticket_id}</b> created. We'll reply here."),
    "support_reply": ("📩 Ответ по тикету <b>#{ticket_id}</b>:\n\n{text}", "📩 Reply to ticket <b>#{ticket_id}</b>:\n\n{text}"),
    "support_closed": ("✅ Тикет <b>#{ticket_id}</b> закрыт.", "✅ Ticket <b>#{ticket_id}</b> closed."),
    "support_no_chat": ("📩 Чат поддержки не настроен (IRIS_SUPPORT_CHAT_ID).", "📩 Support chat is not configured (IRIS_SUPPORT_CHAT_ID)."),
    "report_created": (
        "📩 Жалоба <b>#{report_id}</b> отправлена администраторам.",
        "📩 Report <b>#{report_id}</b> sent to admins.",
    ),
    "report_title": (
        "🚨 <b>Жалоба #{report_id}</b>\n👤 На: {target}\n🙋 От: {reporter}\n📝 {reason}",
        "🚨 <b>Report #{report_id}</b>\n👤 Against: {target}\n🙋 From: {reporter}\n📝 {reason}",
    ),
    "report_none": ("🚨 Открытых жалоб нет.", "🚨 No open reports."),
    "appeal_created": ("⚖️ Апелляция отправлена. Решение сообщим здесь.", "⚖️ Appeal sent. We'll notify you here."),
    "appeal_title": (
        "⚖️ <b>Апелляция #{report_id}</b>\n👤 {reporter}\n📝 {reason}",
        "⚖️ <b>Appeal #{report_id}</b>\n👤 {reporter}\n📝 {reason}",
    ),

    # --- Розыгрыши и голосования ------------------------------------------
    "giveaway_created": (
        "🎁 <b>Розыгрыш:</b> {prize}\n👥 Победителей: {winners}\n⏳ До: {ends}\n\nНажмите кнопку, чтобы участвовать!",
        "🎁 <b>Giveaway:</b> {prize}\n👥 Winners: {winners}\n⏳ Ends: {ends}\n\nPress the button to join!",
    ),
    "giveaway_join": ("✅ Вы участвуете в розыгрыше!", "✅ You joined the giveaway!"),
    "giveaway_joined_already": ("✅ Вы уже участвуете.", "✅ You're already in."),
    "giveaway_ended": ("🎉 Розыгрыш завершён! Победители: {winners}", "🎉 Giveaway finished! Winners: {winners}"),
    "giveaway_none": ("🎁 Активных розыгрышей нет.", "🎁 No active giveaways."),
    "giveaway_usage": (
        "🎁 Пример: <code>ирис розыгрыш 100 Ирисок | 60</code> (приз | минут)",
        "🎁 Example: <code>iris giveaway 100 coins | 60</code> (prize | minutes)",
    ),
    "poll_created": ("🗳️ Голосование создано.", "🗳️ Poll created."),
    "poll_usage": (
        "🗳️ Пример: <code>ирис голосование Вопрос? | Да | Нет</code>",
        "🗳️ Example: <code>iris poll Question? | Yes | No</code>",
    ),
    "poll_vote_ok": ("✅ Голос учтён.", "✅ Vote counted."),
    "poll_results": ("🗳️ <b>{question}</b>\n{lines}", "🗳️ <b>{question}</b>\n{lines}"),
    "poll_closed": ("🔒 Голосование закрыто.", "🔒 Poll closed."),

    # --- Автоматизация -----------------------------------------------------
    "auto_title": ("⚙️ <b>Автоматизация</b>", "⚙️ <b>Automation</b>"),
    "auto_empty": ("⚙️ Автоматизаций нет. Пример: <code>ирис авто добавить слово=привет ответ=Здравствуйте, {user}!</code>", "⚙️ No automations. Example: <code>iris auto add word=hi reply=Hello, {user}!</code>"),
    "auto_created": ("✅ Автоматизация <b>#{id}</b> создана.", "✅ Automation <b>#{id}</b> created."),
    "auto_usage": (
        "⚙️ Ключи: <code>слово=</code>, <code>regex=</code>, <code>ответ=</code>, <code>удалить=1</code>, "
        "<code>мут=минут</code>, <code>пред=1</code>, <code>бан=1</code>, <code>награда=сумма</code>\n"
        "Пример: <code>ирис авто добавить слово=реклама удалить=1 мут=60</code>",
        "⚙️ Keys: <code>word=</code>, <code>regex=</code>, <code>reply=</code>, <code>delete=1</code>, "
        "<code>mute=minutes</code>, <code>warn=1</code>, <code>ban=1</code>, <code>reward=amount</code>",
    ),
    "auto_not_found": ("⚙️ Автоматизация не найдена.", "⚙️ Automation not found."),
    "auto_deleted": ("🗑️ Автоматизация удалена.", "🗑️ Automation deleted."),
    "auto_toggled": ("✅ Автоматизация {state}.", "✅ Automation {state}."),

    # --- Журнал и уведомления ---------------------------------------------
    "audit_title": ("🧾 <b>Журнал действий</b>", "🧾 <b>Audit log</b>"),
    "audit_empty": ("🧾 Журнал пуст.", "🧾 The log is empty."),
    "notifications_on": ("🔔 Уведомления включены.", "🔔 Notifications on."),
    "notifications_off": ("🔕 Уведомления выключены.", "🔕 Notifications off."),

    # --- CAPTCHA -----------------------------------------------------------
    "captcha_join": (
        "👋 {name}, добро пожаловать в <b>{chat}</b>!\n\n"
        "🔐 Подтвердите, что вы человек: нажмите кнопку с ответом <b>{answer}</b>.\n"
        "⏳ У вас {minutes} мин.",
        "👋 {name}, welcome to <b>{chat}</b>!\n\n"
        "🔐 Please confirm you're human: press the button with <b>{answer}</b>.\n"
        "⏳ You have {minutes} min.",
    ),
    "captcha_ok": ("✅ Проверка пройдена, добро пожаловать!", "✅ Verified, welcome!"),
    "captcha_fail": ("❌ Неверно. Попробуйте ещё раз.", "❌ Wrong answer, try again."),
    "captcha_timeout": ("⌛ {name} не прошёл проверку и был исключён.", "⌛ {name} failed the check and was removed."),
    "captcha_disabled": ("🔐 CAPTCHA выключена в этой группе.", "🔐 CAPTCHA is disabled here."),

    # --- Приветствие -------------------------------------------------------
    "welcome_default": (
        "👋 {user}, добро пожаловать в <b>{chat}</b>! Мы рады тебе.\n"
        "Напиши <code>ирис помощь</code>, чтобы узнать возможности.",
        "👋 {user}, welcome to <b>{chat}</b>! Glad to see you.\nType <code>iris help</code> to explore.",
    ),
    "welcome_count": ("👥 Участник #{count}", "👥 Member #{count}"),
}


def escape_html(text: str | None) -> str:
    """Экранирование пользовательского текста для parse_mode=HTML."""
    return html.escape(text or "", quote=False)


class Texts:
    def t(self, locale: str, key: str, **kwargs: object) -> str:
        pair = TEXTS.get(key)
        if pair is None:
            return key
        text = pair[1] if locale.startswith("en") else pair[0]
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                return text
        return text

    def has(self, key: str) -> bool:
        return key in TEXTS


texts = Texts()
