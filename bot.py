import os
import html
import sqlite3
from datetime import datetime, timezone
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, ChatMemberHandler, CommandHandler, ContextTypes

TOKEN = os.environ["BOT_TOKEN"]
DB_PATH = os.environ.get("DB_PATH", "/app/data/pozor.sqlite3")

def db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS exits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            display_name TEXT NOT NULL,
            username TEXT,
            exited_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn

def label(user):
    name = html.escape(user.full_name or "Без имени")
    if user.username:
        return f"@{html.escape(user.username)} ({name})"
    return f'<a href="tg://user?id={user.id}">{name}</a>'

async def on_member_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    change = update.chat_member
    if not change:
        return

    old = change.old_chat_member.status
    new = change.new_chat_member.status
    user = change.new_chat_member.user

    # Record only a genuine transition from a chat member to left/kicked.
    was_member = old in ("member", "administrator", "creator", "restricted")
    has_left = new in ("left", "kicked")
    if not (was_member and has_left) or user.is_bot:
        return

    now = datetime.now(timezone.utc).astimezone().strftime("%d.%m.%Y в %H:%M")
    conn = db()
    conn.execute(
        "INSERT INTO exits (chat_id, user_id, display_name, username, exited_at) VALUES (?, ?, ?, ?, ?)",
        (update.effective_chat.id, user.id, user.full_name, user.username, now)
    )
    conn.commit()
    conn.close()

    message = (
        "🚨 <b>НОВЫЙ НОМИНАНТ НА ДОСКЕ ПОЗОРА</b> 🚨\n\n"
        f"👤 Участник: {label(user)}\n"
        f"📅 Дата: {now}\n\n"
        "Причина: <b>ХУЕСОС И ГОВНО.</b>\n"
        "🏆 Место в истории позора присвоено."
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=message,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

async def pozor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = db()
    rows = conn.execute(
        "SELECT display_name, username, exited_at FROM exits WHERE chat_id=? ORDER BY id DESC LIMIT 10",
        (chat_id,)
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) FROM exits WHERE chat_id=?", (chat_id,)
    ).fetchone()[0]
    conn.close()

    if not rows:
        await update.message.reply_text("Пока доска позора пуста. Наслаждайтесь подозрительным спокойствием 😇")
        return

    lines = [f"🚨 <b>ДОСКА ПОЗОРА</b> — всего записей: <b>{total}</b>\n"]
    for i, (name, username, when) in enumerate(rows, 1):
        who = f"@{html.escape(username)}" if username else html.escape(name)
        lines.append(f"{i}. {who} — {html.escape(when)}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    count = conn.execute(
        "SELECT COUNT(*) FROM exits WHERE chat_id=?", (update.effective_chat.id,)
    ).fetchone()[0]
    conn.close()
    await update.message.reply_text(f"🏃 Всего беглецов зафиксировано: {count}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я веду доску позора. Команды:\n"
        "/pozor — последние 10 записей\n"
        "/stats — общее число выходов"
    )

def main():
    db().close()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(ChatMemberHandler(on_member_change, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pozor", pozor))
    app.add_handler(CommandHandler("stats", stats))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
