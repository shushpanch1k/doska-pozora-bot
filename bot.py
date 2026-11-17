import os
import sqlite3
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from html import escape

from telegram import Update
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
)

# Railway Variables:
# BOT_TOKEN = token from BotFather
# DB_PATH = /app/data/pozor.sqlite3

TOKEN = os.environ["BOT_TOKEN"]
DB_PATH = os.getenv("DB_PATH", "/app/data/pozor.sqlite3")
MOSCOW_TZ = ZoneInfo("Europe/Moscow")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def get_db():
    folder = os.path.dirname(DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS exits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            display_name TEXT NOT NULL,
            username TEXT,
            exited_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def format_person(username, display_name):
    safe_name = escape(display_name or "Без имени")
    if username:
        safe_username = escape(username)
        return f"@{safe_username} ({safe_name})"
    return safe_name


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Привет! Я веду доску позора этого чата. 💀\n\n"
        "/pozor — посмотреть список выбывших\n"
        "/stats — статистика выходов"
    )


async def on_member_change(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    change = update.chat_member
    if change is None:
        return

    old_status = change.old_chat_member.status
    new_status = change.new_chat_member.status
    user = change.new_chat_member.user

    member_statuses = {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
        ChatMemberStatus.RESTRICTED,
    }
    left_statuses = {
        ChatMemberStatus.LEFT,
        ChatMemberStatus.BANNED,
    }

    # Записываем только реальный переход из участника в вышедшие/заблокированные.
    if old_status not in member_statuses or new_status not in left_statuses:
        return
    if user.is_bot:
        return

    now = datetime.now(MOSCOW_TZ).strftime("%d.%m.%Y в %H:%M")
    conn = get_db()
    conn.execute(
        """
        INSERT INTO exits (chat_id, user_id, display_name, username, exited_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            update.effective_chat.id,
            user.id,
            user.full_name,
            user.username,
            now,
        ),
    )
    conn.commit()
    conn.close()

    username = f"@{user.username}" if user.username else "нет username"
    display_name = escape(user.full_name or "Без имени")
    safe_username = escape(username)

    message = (
        "🚨 <b>НОВЫЙ НОМИНАНТ НА ДОСКЕ ПОЗОРА</b> 🚨\n\n"
        f"👤 Участник: {safe_username} ({display_name})\n"
        f"📅 Дата: {now}\n\n"
        "Причина: Сбежал с позором.\n"
        "🏆 Место в истории позора присвоено.\n\n"
        "📋 Чтобы посмотреть весь список, нажмите /pozor"
    )

    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=message,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("Не удалось отправить сообщение о выходе участника")


async def pozor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = get_db()
    rows = conn.execute(
        """
        SELECT display_name, username, exited_at
        FROM exits
        WHERE chat_id = ?
        ORDER BY id DESC
        """,
        (chat_id,),
    ).fetchall()
    conn.close()

    if not rows:
        await update.effective_message.reply_text(
            "📋 Доска позора пока пуста. Никто ещё не сбежал!"
        )
        return

    total = len(rows)
    header = f"📋 <b>ПОЛНЫЙ СПИСОК ДОСКИ ПОЗОРА</b>\nВсего номинантов: {total}\n\n"
    lines = []
    for number, row in enumerate(rows, start=1):
        person = format_person(row["username"], row["display_name"])
        lines.append(
            f"{number}. {person}\n"
            f"   📅 {escape(row['exited_at'])}"
        )

    # Telegram ограничивает длину сообщения; отправляем список частями.
    current = header
    for line in lines:
        addition = line + "\n\n"
        if len(current) + len(addition) > 3800:
            await update.effective_message.reply_text(
                current, parse_mode="HTML"
            )
            current = ""
        current += addition

    if current:
        await update.effective_message.reply_text(current, parse_mode="HTML")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) AS total FROM exits WHERE chat_id = ?",
        (chat_id,),
    ).fetchone()
    conn.close()

    await update.effective_message.reply_text(
        f"📊 Всего выходов из чата: {row['total']}"
    )


def main():
    # Один polling-процесс должен работать с этим токеном.
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pozor", pozor))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(
        ChatMemberHandler(on_member_change, ChatMemberHandler.CHAT_MEMBER)
    )

    logger.info("Бот запускается. Часовой пояс: Москва.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
