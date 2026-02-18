import asyncio
import logging
import os
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import Database
from scraper import JobScraper

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Load env
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHECK_INTERVAL_MINUTES = int(os.environ.get("CHECK_INTERVAL_MINUTES", "60"))

db = Database()
scraper = JobScraper()


# ─────────────────────────────────────────────
#  COMMANDS
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.first_name or "User")

    keyboard = [
        [InlineKeyboardButton("📋 Mga Pinakabagong Jobs", callback_data="latest_jobs")],
        [
            InlineKeyboardButton("✅ Mag-Subscribe", callback_data="subscribe"),
            InlineKeyboardButton("❌ I-Unsubscribe", callback_data="unsubscribe"),
        ],
        [InlineKeyboardButton("⚙️ I-filter ang Jobs", callback_data="filter_menu")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome = (
        f"👋 *Kumusta {user.first_name}!*\n\n"
        "Ako ang iyong *PH Job Hunter Bot* 🤖\n\n"
        "Naghahanap ako ng mga *LEGIT* na trabaho sa:\n"
        "🏢 *Call Center / BPO*\n"
        "💻 *Virtual Assistant (VA)*\n"
        "🎰 *POGO / Online Gaming*\n"
        "🌐 *Remote / Work From Home*\n\n"
        "I-update kita kapag may *bagong job posting* mula sa:\n"
        "• JobStreet PH\n"
        "• OnlineJobs.ph (RSS)\n"
        "• Indeed PH\n"
        "• Jooble PH\n\n"
        "Piliin ang aksyon sa baba 👇"
    )

    await update.message.reply_text(welcome, parse_mode="Markdown", reply_markup=reply_markup)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 *Mga Commands:*\n\n"
        "/start - Simulan ang bot\n"
        "/jobs - Pinakabagong 10 job posts\n"
        "/subscribe - Mag-subscribe sa job alerts\n"
        "/unsubscribe - I-stop ang alerts\n"
        "/filter - I-set ang job type preference\n"
        "/status - Tingnan ang iyong subscription status\n"
        "/stats - Bot statistics\n"
        "/help - Ipakita ang tulong na ito\n\n"
        "🔔 *Paano gumagana:*\n"
        "Kapag nag-subscribe ka, aabisuhan kita ng *real-time* kapag may bagong job na posted!"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_latest_jobs(update.message.chat_id, context.bot, limit=10)


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.first_name or "User")
    db.subscribe_user(user.id)
    await update.message.reply_text(
        "✅ *Naka-subscribe ka na!*\n\n"
        "Aabisuhan kita kapag may bagong job posting.\n"
        "I-type /unsubscribe kung gusto mong ihinto.",
        parse_mode="Markdown",
    )


async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.unsubscribe_user(update.effective_user.id)
    await update.message.reply_text(
        "❌ *Na-unsubscribe ka na.*\n\n"
        "Hindi ka na makakatanggap ng job alerts.\n"
        "I-type /subscribe para bumalik.",
        parse_mode="Markdown",
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)

    if not user_data:
        await update.message.reply_text("Wala pa akong record sa iyo. I-type /start muna.")
        return

    is_subscribed = bool(user_data["subscribed"])
    filters = user_data["filters"] or "Lahat ng klase ng trabaho"
    status_icon = "✅" if is_subscribed else "❌"

    await update.message.reply_text(
        f"📊 *Iyong Status:*\n\n"
        f"{status_icon} Subscription: {'Active' if is_subscribed else 'Inactive'}\n"
        f"🔍 Filters: {filters}\n"
        f"📅 Sumali: {user_data['joined_at']}",
        parse_mode="Markdown",
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users = db.count_users()
    subscribed = db.count_subscribed()
    total_jobs = db.count_jobs()
    jobs_today = db.count_jobs_today()

    await update.message.reply_text(
        f"📊 *Bot Statistics:*\n\n"
        f"👥 Total Users: {total_users}\n"
        f"🔔 Subscribed: {subscribed}\n"
        f"💼 Total Jobs Found: {total_jobs}\n"
        f"🆕 Bagong Jobs Ngayon: {jobs_today}\n"
        f"⏱ Check Interval: bawat {CHECK_INTERVAL_MINUTES} minuto",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────
#  CALLBACK BUTTONS
# ─────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user = query.from_user

    if data == "latest_jobs":
        await query.message.reply_text("🔍 Hihanapin ko ang pinakabagong jobs...")
        await send_latest_jobs(query.message.chat_id, context.bot, limit=10)

    elif data == "subscribe":
        db.add_user(user.id, user.first_name or "User")
        db.subscribe_user(user.id)
        await query.message.reply_text(
            "✅ *Naka-subscribe ka na!*\nAabisuhan kita ng bagong job posts.",
            parse_mode="Markdown",
        )

    elif data == "unsubscribe":
        db.unsubscribe_user(user.id)
        await query.message.reply_text(
            "❌ Na-unsubscribe ka na. I-type /subscribe para bumalik.",
            parse_mode="Markdown",
        )

    elif data == "filter_menu":
        keyboard = [
            [InlineKeyboardButton("🏢 Call Center / BPO", callback_data="filter_callcenter")],
            [InlineKeyboardButton("💻 Virtual Assistant", callback_data="filter_va")],
            [InlineKeyboardButton("🎰 POGO / Online Gaming", callback_data="filter_pogo")],
            [InlineKeyboardButton("🌐 Remote / WFH", callback_data="filter_remote")],
            [InlineKeyboardButton("📋 Lahat ng Trabaho", callback_data="filter_all")],
        ]
        await query.message.reply_text(
            "⚙️ *Piliin ang job type na gusto mo:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("filter_"):
        filter_map = {
            "filter_callcenter": "Call Center / BPO",
            "filter_va": "Virtual Assistant",
            "filter_pogo": "POGO / Online Gaming",
            "filter_remote": "Remote / WFH",
            "filter_all": "Lahat",
        }
        chosen = filter_map.get(data, "Lahat")
        db.set_filter(user.id, chosen)
        await query.message.reply_text(
            f"✅ *Filter na-set sa:* {chosen}\n\nMatatanggap mo na lang ang mga {chosen} jobs.",
            parse_mode="Markdown",
        )

    elif data == "stats":
        total_users = db.count_users()
        subscribed = db.count_subscribed()
        total_jobs = db.count_jobs()
        jobs_today = db.count_jobs_today()
        await query.message.reply_text(
            f"📊 *Bot Statistics:*\n\n"
            f"👥 Total Users: {total_users}\n"
            f"🔔 Subscribed: {subscribed}\n"
            f"💼 Total Jobs Found: {total_jobs}\n"
            f"🆕 Bagong Jobs Ngayon: {jobs_today}",
            parse_mode="Markdown",
        )


# ─────────────────────────────────────────────
#  JOB BROADCAST
# ─────────────────────────────────────────────

async def send_latest_jobs(chat_id: int, bot, limit: int = 10):
    jobs = db.get_latest_jobs(limit=limit)

    if not jobs:
        await bot.send_message(
            chat_id=chat_id,
            text="😔 Wala pang nakuhang jobs. Subukan ulit mamaya.",
        )
        return

    await bot.send_message(chat_id=chat_id, text=f"💼 *{len(jobs)} Pinakabagong Jobs:*", parse_mode="Markdown")

    for job in jobs:
        msg = format_job_message(job)
        try:
            await bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown", disable_web_page_preview=True)
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"Error sending job to {chat_id}: {e}")


def format_job_message(job: dict) -> str:
    category_icons = {
        "Call Center / BPO": "🏢",
        "Virtual Assistant": "💻",
        "POGO / Online Gaming": "🎰",
        "Remote / WFH": "🌐",
    }
    icon = category_icons.get(job.get("category", ""), "💼")

    date_str = job.get("date_found", "")
    if isinstance(date_str, str) and len(date_str) > 10:
        date_str = date_str[:16]

    return (
        f"{icon} *{job['title']}*\n"
        f"🏢 {job['company']}\n"
        f"📂 {job.get('category', 'General')}\n"
        f"📍 {job.get('location', 'Philippines')}\n"
        f"🌐 Source: {job['source']}\n"
        f"📅 {date_str}\n"
        f"🔗 [I-apply dito!]({job['link']})"
    )


async def broadcast_new_jobs(bot):
    """Called by scheduler - scrape at i-broadcast sa subscribers"""
    logger.info("🔍 Nagsisimula ang job scraping...")

    try:
        new_jobs = await scraper.scrape_all()
        logger.info(f"✅ Nakakuha ng {len(new_jobs)} potential jobs")
    except Exception as e:
        logger.error(f"Scraping error: {e}")
        return

    saved_jobs = []
    for job in new_jobs:
        if db.save_job(job):
            saved_jobs.append(job)

    logger.info(f"🆕 {len(saved_jobs)} bagong jobs ang nakita")

    if not saved_jobs:
        return

    subscribers = db.get_subscribers()
    logger.info(f"📤 Magse-send sa {len(subscribers)} subscribers")

    for user in subscribers:
        user_filter = user.get("filters", "Lahat")

        jobs_to_send = [
            j for j in saved_jobs
            if user_filter == "Lahat" or j.get("category") == user_filter
        ]

        if not jobs_to_send:
            continue

        try:
            await bot.send_message(
                chat_id=user["user_id"],
                text=f"🔔 *{len(jobs_to_send)} BAGONG JOB POSTING{'S' if len(jobs_to_send) > 1 else ''}!*",
                parse_mode="Markdown",
            )
            for job in jobs_to_send[:5]:  # max 5 per broadcast para hindi spam
                msg = format_job_message(job)
                await bot.send_message(
                    chat_id=user["user_id"],
                    text=msg,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
                await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"Broadcast error for user {user['user_id']}: {e}")
            # If blocked, unsubscribe
            if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                db.unsubscribe_user(user["user_id"])


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN environment variable is not set!")

    db.init_db()
    logger.info("✅ Database initialized")

    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("jobs", jobs_command))
    app.add_handler(CommandHandler("subscribe", subscribe_command))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        broadcast_new_jobs,
        "interval",
        minutes=CHECK_INTERVAL_MINUTES,
        args=[app.bot],
        next_run_time=datetime.now(),  # run agad upon start
    )
    scheduler.start()
    logger.info(f"⏱ Scheduler started - checking every {CHECK_INTERVAL_MINUTES} minutes")

    logger.info("🤖 Bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
