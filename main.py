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
    MessageHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import Database
from scraper import JobScraper

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHECK_INTERVAL_MINUTES = int(os.environ.get("CHECK_INTERVAL_MINUTES", "60"))
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))  # optional - para sa admin commands

db = Database()
scraper = JobScraper()

# ═══════════════════════════════════════════════════════════════════════════════
#  HELPER TEXTS
# ═══════════════════════════════════════════════════════════════════════════════

CATEGORY_ICONS = {
    "Call Center / BPO": "📞",
    "Virtual Assistant": "💻",
    "POGO / Online Gaming": "🎰",
    "Remote / WFH": "🏠",
    "Accounting / Finance": "💰",
    "IT / Tech": "🖥️",
    "Sales / Marketing": "📈",
    "Healthcare": "🏥",
    "General": "💼",
}

SOURCE_ICONS = {
    "Indeed PH": "🔵",
    "JobStreet PH": "🟢",
    "OnlineJobs.ph": "🟡",
    "Jooble": "🟣",
    "Kalibrr": "🔴",
    "LinkedIn": "🔷",
    "Trabaho.ph": "🟠",
    "BossJob PH": "⚫",
    "PhilJobNet": "🇵🇭",
    "Workable PH": "🔸",
}


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN MENU
# ═══════════════════════════════════════════════════════════════════════════════

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Pinakabagong Jobs", callback_data="latest_jobs")],
        [
            InlineKeyboardButton("🔔 Mag-Subscribe", callback_data="subscribe"),
            InlineKeyboardButton("🔕 I-stop Alerts", callback_data="unsubscribe"),
        ],
        [InlineKeyboardButton("⚙️ Piliin ang Job Type", callback_data="filter_menu")],
        [
            InlineKeyboardButton("📊 Aking Status", callback_data="my_status"),
            InlineKeyboardButton("📈 Bot Stats", callback_data="stats"),
        ],
        [InlineKeyboardButton("❓ Tulong / Help", callback_data="help")],
    ])


# ═══════════════════════════════════════════════════════════════════════════════
#  COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_new = db.add_user(user.id, user.first_name or "Kabayan")

    greeting = "Maligayang pagdating" if is_new else "Muli kang nakabalik"

    welcome = (
        f"👋 *{greeting}, {user.first_name}!*\n\n"
        "Ako si *PH Job Finder Bot* 🤖🇵🇭\n"
        "Tumutulong ako sa mga Pilipino na makahanap ng *legit at updated* na trabaho!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💼 *Mga Trabahong Hinahanap Ko:*\n\n"
        "📞 Call Center / BPO / CSR\n"
        "💻 Virtual Assistant (VA)\n"
        "🎰 POGO / Online Gaming\n"
        "🏠 Remote / Work From Home\n"
        "💰 Accounting / Finance\n"
        "🖥️ IT / Tech Support\n"
        "📈 Sales / Marketing\n"
        "🏥 Healthcare / Nursing\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🌐 *Mga Pinagkukuhaan ng Jobs:*\n"
        "Indeed PH • JobStreet • LinkedIn\n"
        "OnlineJobs.ph • Kalibrr • Jooble\n"
        "Trabaho.ph • BossJob • PhilJobNet\n\n"
        "📲 *I-tap ang button sa baba para magsimula!* 👇"
    )

    await update.message.reply_text(
        welcome, parse_mode="Markdown", reply_markup=main_menu_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "❓ *Mga Available na Commands:*\n\n"
        "/start — Pangunahing menu\n"
        "/jobs — Pinakabagong 15 job posts\n"
        "/subscribe — Mag-on ng job alert notifications\n"
        "/unsubscribe — Mag-off ng notifications\n"
        "/filter — Piliin ang klase ng trabaho\n"
        "/status — Tingnan ang iyong settings\n"
        "/stats — Mga bilang at statistics ng bot\n"
        "/help — Itong tulong na ito\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔔 *Paano gumagana ang bot?*\n\n"
        "1️⃣ I-tap ang *Mag-Subscribe*\n"
        "2️⃣ Piliin ang gusto mong *job type*\n"
        "3️⃣ Aabisuhan ka ng bot kapag may *bagong posting*!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⏱ *Gaano kadalas mag-update?*\n"
        f"Bawat *{CHECK_INTERVAL_MINUTES} minuto* nag-che-check ang bot ng bagong jobs.\n\n"
        "💡 *Tip:* Mag-filter ka ng specific na job type para mas relevant ang makukuha mong notifications!"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())


async def jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = db.get_user(update.effective_user.id)
    user_filter = user_data.get("filters", "Lahat") if user_data else "Lahat"
    await update.message.reply_text("⏳ *Sandali lang, hinahanap ko ang mga jobs...*", parse_mode="Markdown")
    await send_latest_jobs(update.message.chat_id, context.bot, limit=15, category_filter=user_filter)


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.first_name or "Kabayan")
    db.subscribe_user(user.id)
    await update.message.reply_text(
        "🔔 *Naka-subscribe ka na!*\n\n"
        "✅ Aabisuhan kita tuwing may bagong job posting.\n"
        "⚙️ I-type /filter para piliin ang specific na job type.\n"
        "🔕 I-type /unsubscribe para ihinto ang alerts.",
        parse_mode="Markdown",
    )


async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.unsubscribe_user(update.effective_user.id)
    await update.message.reply_text(
        "🔕 *Na-off na ang iyong job alerts.*\n\n"
        "Hindi ka na makakatanggap ng notifications.\n"
        "I-type /subscribe para bumalik anumang oras! 😊",
        parse_mode="Markdown",
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)

    if not user_data:
        await update.message.reply_text(
            "Wala pa akong record sa iyo. I-type /start para magsimula! 😊"
        )
        return

    is_sub = bool(user_data["subscribed"])
    user_filter = user_data["filters"] or "Lahat"
    sub_icon = "🟢" if is_sub else "🔴"
    sub_text = "AKTIBO — tumatanggap ka ng alerts" if is_sub else "HINDI AKTIBO — hindi tumatanggap ng alerts"

    await update.message.reply_text(
        f"📊 *Iyong Account Status:*\n\n"
        f"{sub_icon} Subscription: {sub_text}\n"
        f"⚙️ Job Filter: *{user_filter}*\n"
        f"📅 Sumali noong: {user_data['joined_at'][:10]}\n\n"
        f"I-tap ang /filter para baguhin ang job type preference.",
        parse_mode="Markdown",
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users = db.count_users()
    subscribed = db.count_subscribed()
    total_jobs = db.count_jobs()
    jobs_today = db.count_jobs_today()
    sources = db.count_by_source()

    source_lines = "\n".join(
        f"  {SOURCE_ICONS.get(s['source'], '•')} {s['source']}: {s['count']} jobs"
        for s in sources[:8]
    )

    await update.message.reply_text(
        f"📈 *Bot Statistics:*\n\n"
        f"👥 Kabuuang Users: *{total_users}*\n"
        f"🔔 Naka-subscribe: *{subscribed}*\n"
        f"💼 Kabuuang Jobs na Nakita: *{total_jobs}*\n"
        f"🆕 Bagong Jobs Ngayon: *{jobs_today}*\n\n"
        f"📡 *Jobs per Source:*\n{source_lines or '  Wala pang data'}",
        parse_mode="Markdown",
    )


# ─── Admin: Force scrape now ───────────────────────────────────────────────────
async def scrape_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_ID and user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only ang command na ito.")
        return
    await update.message.reply_text("🔍 Sisimulan ko ang manual scraping ngayon...")
    await broadcast_new_jobs(context.bot)
    await update.message.reply_text("✅ Tapos na ang scraping!")


# ═══════════════════════════════════════════════════════════════════════════════
#  CALLBACK BUTTONS
# ═══════════════════════════════════════════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    if data == "latest_jobs":
        user_data = db.get_user(user.id)
        user_filter = user_data.get("filters", "Lahat") if user_data else "Lahat"
        await query.message.reply_text("⏳ *Sandali lang, hinahanap ko ang mga jobs...*", parse_mode="Markdown")
        await send_latest_jobs(query.message.chat_id, context.bot, limit=15, category_filter=user_filter)

    elif data == "subscribe":
        db.add_user(user.id, user.first_name or "Kabayan")
        db.subscribe_user(user.id)
        await query.message.reply_text(
            "🔔 *Naka-subscribe ka na!*\n\n"
            "✅ Aabisuhan kita ng bagong job posts.\n"
            "⚙️ Pwede ka ring mag-filter ng job type gamit ang /filter.",
            parse_mode="Markdown",
        )

    elif data == "unsubscribe":
        db.unsubscribe_user(user.id)
        await query.message.reply_text(
            "🔕 *Na-off na ang iyong alerts.*\n"
            "I-tap ang /subscribe para bumalik anumang oras.",
            parse_mode="Markdown",
        )

    elif data == "filter_menu":
        keyboard = [
            [InlineKeyboardButton("📋 Lahat ng Trabaho", callback_data="filter_all")],
            [InlineKeyboardButton("📞 Call Center / BPO", callback_data="filter_callcenter")],
            [InlineKeyboardButton("💻 Virtual Assistant (VA)", callback_data="filter_va")],
            [InlineKeyboardButton("🎰 POGO / Online Gaming", callback_data="filter_pogo")],
            [InlineKeyboardButton("🏠 Remote / Work From Home", callback_data="filter_remote")],
            [InlineKeyboardButton("💰 Accounting / Finance", callback_data="filter_accounting")],
            [InlineKeyboardButton("🖥️ IT / Tech Support", callback_data="filter_it")],
            [InlineKeyboardButton("📈 Sales / Marketing", callback_data="filter_sales")],
            [InlineKeyboardButton("🏥 Healthcare / Nursing", callback_data="filter_healthcare")],
        ]
        await query.message.reply_text(
            "⚙️ *Piliin ang job type na gusto mo:*\n\n"
            "Matatanggap mo lang ang notifications para sa napiling klase ng trabaho.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("filter_"):
        filter_map = {
            "filter_all": "Lahat",
            "filter_callcenter": "Call Center / BPO",
            "filter_va": "Virtual Assistant",
            "filter_pogo": "POGO / Online Gaming",
            "filter_remote": "Remote / WFH",
            "filter_accounting": "Accounting / Finance",
            "filter_it": "IT / Tech",
            "filter_sales": "Sales / Marketing",
            "filter_healthcare": "Healthcare",
        }
        chosen = filter_map.get(data, "Lahat")
        db.add_user(user.id, user.first_name or "Kabayan")
        db.set_filter(user.id, chosen)
        icon = CATEGORY_ICONS.get(chosen, "💼")
        await query.message.reply_text(
            f"✅ *Na-set ang filter mo sa:*\n{icon} {chosen}\n\n"
            f"Mga {chosen} jobs lang ang ipapakita sa iyo ngayon.",
            parse_mode="Markdown",
        )

    elif data == "my_status":
        user_data = db.get_user(user.id)
        if not user_data:
            await query.message.reply_text("I-type /start muna para mag-register. 😊")
            return
        is_sub = bool(user_data["subscribed"])
        sub_icon = "🟢" if is_sub else "🔴"
        sub_text = "AKTIBO" if is_sub else "HINDI AKTIBO"
        await query.message.reply_text(
            f"📊 *Iyong Status:*\n\n"
            f"{sub_icon} Subscription: {sub_text}\n"
            f"⚙️ Filter: *{user_data.get('filters', 'Lahat')}*\n"
            f"📅 Sumali: {str(user_data['joined_at'])[:10]}",
            parse_mode="Markdown",
        )

    elif data == "stats":
        total_users = db.count_users()
        subscribed = db.count_subscribed()
        total_jobs = db.count_jobs()
        jobs_today = db.count_jobs_today()
        await query.message.reply_text(
            f"📈 *Bot Statistics:*\n\n"
            f"👥 Kabuuang Users: *{total_users}*\n"
            f"🔔 Naka-subscribe: *{subscribed}*\n"
            f"💼 Kabuuang Jobs na Nakita: *{total_jobs}*\n"
            f"🆕 Bagong Jobs Ngayon: *{jobs_today}*",
            parse_mode="Markdown",
        )

    elif data == "help":
        await help_command(query, context)


# ═══════════════════════════════════════════════════════════════════════════════
#  JOB DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

async def send_latest_jobs(chat_id: int, bot, limit: int = 15, category_filter: str = "Lahat"):
    if category_filter and category_filter != "Lahat":
        jobs = db.get_latest_jobs_by_category(category=category_filter, limit=limit)
    else:
        jobs = db.get_latest_jobs(limit=limit)

    if not jobs:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "😔 *Wala pang nakuhang jobs sa ngayon.*\n\n"
                "Mag-antay ka sandali — bawat ilang minuto ay nag-che-check ang bot ng bagong postings. "
                "Subukan ulit mamaya! 🙏"
            ),
            parse_mode="Markdown",
        )
        return

    filter_text = f" ({category_filter})" if category_filter != "Lahat" else ""
    await bot.send_message(
        chat_id=chat_id,
        text=f"💼 *{len(jobs)} Pinakabagong Jobs{filter_text}:*",
        parse_mode="Markdown",
    )

    for job in jobs:
        msg = format_job_message(job)
        try:
            await bot.send_message(
                chat_id=chat_id, text=msg, parse_mode="Markdown", disable_web_page_preview=True
            )
            await asyncio.sleep(0.4)
        except Exception as e:
            logger.error(f"Error sending job to {chat_id}: {e}")


def format_job_message(job: dict) -> str:
    category = job.get("category", "General")
    source = job.get("source", "")
    icon = CATEGORY_ICONS.get(category, "💼")
    src_icon = SOURCE_ICONS.get(source, "🌐")

    date_str = str(job.get("date_found", ""))[:16]

    salary = f"\n💵 {job['salary']}" if job.get("salary") else ""

    return (
        f"{icon} *{job['title']}*\n"
        f"🏢 {job.get('company', 'Hindi nabanggit')}\n"
        f"📂 {category}\n"
        f"📍 {job.get('location', 'Philippines')}"
        f"{salary}\n"
        f"{src_icon} {source} · 📅 {date_str}\n"
        f"🔗 [I-apply dito!]({job['link']})"
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  BROADCAST SCHEDULER
# ═══════════════════════════════════════════════════════════════════════════════

async def broadcast_new_jobs(bot):
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

    logger.info(f"🆕 {len(saved_jobs)} bagong (unique) jobs ang na-save")

    if not saved_jobs:
        logger.info("Walang bagong jobs — walang ibe-broadcast.")
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
            total = len(jobs_to_send)
            await bot.send_message(
                chat_id=user["user_id"],
                text=(
                    f"🔔 *{total} BAGONG JOB POSTING{'S' if total > 1 else ''} NGAYON!* 🇵🇭\n\n"
                    f"Narito ang pinakabago para sa iyo. Huwag palampasin! 💪"
                ),
                parse_mode="Markdown",
            )
            for job in jobs_to_send[:5]:
                msg = format_job_message(job)
                await bot.send_message(
                    chat_id=user["user_id"],
                    text=msg,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
                await asyncio.sleep(0.4)

            if total > 5:
                await bot.send_message(
                    chat_id=user["user_id"],
                    text=f"➕ At *{total - 5} pa* na bagong jobs! I-type /jobs para makita lahat.",
                    parse_mode="Markdown",
                )
        except Exception as e:
            logger.error(f"Broadcast error for {user['user_id']}: {e}")
            if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                db.unsubscribe_user(user["user_id"])


# ─── Fallback unknown command ──────────────────────────────────────────────────
async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hindi ko maintindihan yung sinabi mo. 😅\n"
        "I-type /help para makita ang mga available na commands!",
        reply_markup=main_menu_keyboard(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN environment variable is not set!")

    db.init_db()
    logger.info("✅ Database initialized")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("jobs", jobs_command))
    app.add_handler(CommandHandler("subscribe", subscribe_command))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("scrapnow", scrape_now_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        broadcast_new_jobs,
        "interval",
        minutes=CHECK_INTERVAL_MINUTES,
        args=[app.bot],
        next_run_time=datetime.now(),
    )
    scheduler.start()
    logger.info(f"⏱ Scheduler started — nag-che-check bawat {CHECK_INTERVAL_MINUTES} minuto")

    logger.info("🤖 PH Job Finder Bot ay tumatakbo na!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
