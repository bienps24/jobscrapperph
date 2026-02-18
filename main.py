import asyncio
import logging
import os
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
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
BOT_TOKEN              = os.environ.get("BOT_TOKEN", "")
CHECK_INTERVAL_MINUTES = int(os.environ.get("CHECK_INTERVAL_MINUTES", "60"))
ADMIN_ID               = int(os.environ.get("ADMIN_ID", "0"))
# Group/Channel Chat ID where the bot will post jobs (optional)
# Example: -1001234567890  ← must be a negative number for groups
GROUP_CHAT_ID          = os.environ.get("GROUP_CHAT_ID", "")

db      = Database()
scraper = JobScraper()

# ═══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

CATEGORY_ICONS = {
    "Call Center / BPO":    "📞",
    "Virtual Assistant":    "💻",
    "POGO / Online Gaming": "🎰",
    "Remote / WFH":         "🏠",
    "Accounting / Finance": "💰",
    "IT / Tech":            "🖥️",
    "Sales / Marketing":    "📈",
    "Healthcare":           "🏥",
    "General":              "💼",
}

SOURCE_ICONS = {
    "Indeed PH":     "🔵",
    "JobStreet PH":  "🟢",
    "OnlineJobs.ph": "🟡",
    "Jooble":        "🟣",
    "Kalibrr":       "🔴",
    "LinkedIn":      "🔷",
    "Trabaho.ph":    "🟠",
    "BossJob PH":    "⚫",
    "PhilJobNet":    "🇵🇭",
    "RemoteOK":         "🔸",
    "Glassdoor PH":    "🟤",
    "Monster PH":      "🟥",
    "Upwork":          "🟩",
    "Freelancer.com":  "🔹",
    "JobsDB PH":       "🟦",
    "BestJobs PH":     "🌟",
    "OLX PH Jobs":     "🟧",
    "Google Jobs":     "🔎",
    "Telegram PH Jobs":"✈️",
}

# Bottom reply keyboard button labels
BTN_HELP    = "❓ Help"
BTN_PRIVACY = "📋 Terms & Privacy"
BTN_JOBS    = "🔍 Latest Jobs"
BTN_MENU    = "🏠 Menu"
BTN_SUB     = "🔔 Subscribe"
BTN_FILTER  = "⚙️ Job Filter"


# ═══════════════════════════════════════════════════════════════════════════════
#  KEYBOARDS
# ═══════════════════════════════════════════════════════════════════════════════

def bottom_keyboard():
    """
    Persistent keyboard at the bottom of the chat.
    Only visible in private/direct messages — never shown in group posts.
    """
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_JOBS),   KeyboardButton(BTN_SUB)],
            [KeyboardButton(BTN_FILTER), KeyboardButton(BTN_MENU)],
            [KeyboardButton(BTN_HELP),   KeyboardButton(BTN_PRIVACY)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Choose an action or type a command...",
    )


def main_menu_inline():
    """Inline buttons inside the message — used for the main menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Latest Jobs",         callback_data="latest_jobs")],
        [
            InlineKeyboardButton("🔔 Subscribe",        callback_data="subscribe"),
            InlineKeyboardButton("🔕 Stop Alerts",      callback_data="unsubscribe"),
        ],
        [InlineKeyboardButton("⚙️ Choose Job Type",     callback_data="filter_menu")],
        [
            InlineKeyboardButton("📊 My Status",        callback_data="my_status"),
            InlineKeyboardButton("📈 Bot Stats",        callback_data="stats"),
        ],
        [
            InlineKeyboardButton("❓ Help",             callback_data="help"),
            InlineKeyboardButton("📋 Terms & Privacy",  callback_data="privacy"),
        ],
    ])


# ═══════════════════════════════════════════════════════════════════════════════
#  PRIVACY & TERMS TEXT
# ═══════════════════════════════════════════════════════════════════════════════

PRIVACY_TEXT = """
📋 *Terms of Service & Privacy Policy*
━━━━━━━━━━━━━━━━━━━━━━

🤖 *About This Bot*
*Job Scrapper PH* is an automated service that collects publicly available job postings from various websites to help job seekers in the Philippines find employment opportunities.

━━━━━━━━━━━━━━━━━━━━━━
📌 *Terms of Use*

✅ *Allowed:*
• Use for personal job searching
• Share job listings with friends and family
• Subscribe and filter jobs based on your preference

❌ *Not Allowed:*
• Using the bot for spam or scam activities
• Posting fake job listings
• Using for any illegal purpose
• Scraping the bot's data for personal gain

━━━━━━━━━━━━━━━━━━━━━━
🔒 *Privacy & Data*

• We only collect your *Telegram User ID* and *name* to send job notifications.
• We *do not share* your personal information with anyone.
• We *do not monitor* your messages or activities outside the bot.
• You may request deletion of your data at any time using /deletedata.
• Your subscription and filter preferences are stored in our database.

━━━━━━━━━━━━━━━━━━━━━━
⚠️ *Disclaimer*

• This bot does *not* guarantee the accuracy of job listings.
• All job postings are sourced from *third-party websites* — we are not the employer.
• Always *verify the legitimacy* of an employer before applying.
• Be cautious of employers asking for *payment to get a job* — that is a scam!

━━━━━━━━━━━━━━━━━━━━━━
📞 *Contact*
Reach out to the bot admin if you have any concerns or questions.

_By continuing to use this bot, you agree to these terms._
""".strip()


# ═══════════════════════════════════════════════════════════════════════════════
#  COMMANDS — PRIVATE CHAT ONLY (unless stated)
# ═══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Do not respond to /start in group chats
    if update.effective_chat.type != "private":
        return

    user     = update.effective_user
    is_new   = db.add_user(user.id, user.first_name or "there")
    greeting = "Welcome" if is_new else "Welcome back"

    welcome = (
        f"👋 *{greeting}, {user.first_name}!*\n\n"
        "I'm *Job Scrapper PH* 🤖🇵🇭\n"
        "I help Filipinos find *legit and updated* job opportunities!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💼 *Job Categories I Search:*\n\n"
        "📞 Call Center / BPO / CSR\n"
        "💻 Virtual Assistant (VA)\n"
        "🎰 POGO / Online Gaming\n"
        "🏠 Remote / Work From Home\n"
        "💰 Accounting / Finance\n"
        "🖥️ IT / Tech Support\n"
        "📈 Sales / Marketing\n"
        "🏥 Healthcare / Nursing\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🌐 *Job Sources:*\n"
        "Indeed PH • JobStreet • LinkedIn\n"
        "OnlineJobs.ph • Kalibrr • Jooble\n"
        "Trabaho.ph • BossJob • PhilJobNet\n\n"
        "📲 *Use the buttons below to get started!* 👇"
    )

    await update.message.reply_text(
        welcome,
        parse_mode="Markdown",
        reply_markup=bottom_keyboard(),
    )
    await update.message.reply_text(
        "🏠 *Main Menu:*",
        parse_mode="Markdown",
        reply_markup=main_menu_inline(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    text = (
        "❓ *Help & Commands*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📱 *Available Commands:*\n\n"
        "/start — Main menu\n"
        "/jobs — Show latest 15 job posts\n"
        "/subscribe — Turn on job alert notifications\n"
        "/unsubscribe — Turn off notifications\n"
        "/filter — Choose your preferred job type\n"
        "/status — View your subscription settings\n"
        "/stats — Bot statistics\n"
        "/privacy — Terms & Privacy Policy\n"
        "/deletedata — Delete your personal data\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔔 *How does the bot work?*\n\n"
        "1️⃣ Tap the 🔔 *Subscribe* button\n"
        "2️⃣ Choose your preferred *job type* via Filter\n"
        "3️⃣ The bot will notify you whenever a *new job is posted*!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱ *How often does it update?*\n"
        f"Every *{CHECK_INTERVAL_MINUTES} minutes* the bot checks for new jobs.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 *Tips:*\n"
        "• Set a job filter so you only get relevant notifications\n"
        "• Never pay to get a job — that's a scam!\n"
        "• Always verify the employer before applying\n\n"
        "🆘 Contact the bot admin if you have any issues."
    )
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu_inline(),
    )


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    await update.message.reply_text(
        PRIVACY_TEXT,
        parse_mode="Markdown",
        reply_markup=main_menu_inline(),
    )


async def jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_private = update.effective_chat.type == "private"
    if is_private:
        user_data   = db.get_user(update.effective_user.id)
        user_filter = user_data.get("filters", "All") if user_data else "All"
        # Backward compat: treat old 'Lahat' default as 'All'
        if user_filter == "Lahat":
            user_filter = "All"
    else:
        user_filter = "All"

    await update.message.reply_text(
        "⏳ *Please wait, fetching the latest jobs...*",
        parse_mode="Markdown",
    )
    await send_latest_jobs(
        update.message.chat_id,
        context.bot,
        limit=15,
        category_filter=user_filter,
        is_group=not is_private,
    )


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "💬 To subscribe for personal job alerts, send me a direct message!\n"
            "Click my username to start a private chat. 😊"
        )
        return

    user = update.effective_user
    db.add_user(user.id, user.first_name or "there")
    db.subscribe_user(user.id)
    await update.message.reply_text(
        "🔔 *You are now subscribed!*\n\n"
        "✅ You will be notified whenever new jobs are posted.\n"
        "⚙️ Tap *Job Filter* to choose your preferred job type.\n"
        "🔕 Tap *Stop Alerts* to unsubscribe anytime.",
        parse_mode="Markdown",
        reply_markup=main_menu_inline(),
    )


async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    db.unsubscribe_user(update.effective_user.id)
    await update.message.reply_text(
        "🔕 *Job alerts have been turned off.*\n\n"
        "You will no longer receive notifications.\n"
        "Tap 🔔 *Subscribe* to turn them back on anytime! 😊",
        parse_mode="Markdown",
        reply_markup=main_menu_inline(),
    )


async def filter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    keyboard = [
        [InlineKeyboardButton("📋 All Jobs",               callback_data="filter_all")],
        [InlineKeyboardButton("📞 Call Center / BPO",      callback_data="filter_callcenter")],
        [InlineKeyboardButton("💻 Virtual Assistant (VA)", callback_data="filter_va")],
        [InlineKeyboardButton("🎰 POGO / Online Gaming",   callback_data="filter_pogo")],
        [InlineKeyboardButton("🏠 Remote / Work From Home",callback_data="filter_remote")],
        [InlineKeyboardButton("💰 Accounting / Finance",   callback_data="filter_accounting")],
        [InlineKeyboardButton("🖥️ IT / Tech Support",      callback_data="filter_it")],
        [InlineKeyboardButton("📈 Sales / Marketing",      callback_data="filter_sales")],
        [InlineKeyboardButton("🏥 Healthcare / Nursing",   callback_data="filter_healthcare")],
    ]
    await update.message.reply_text(
        "⚙️ *Choose your preferred Job Type:*\n\n"
        "You will only receive notifications for the selected category.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    user_data = db.get_user(update.effective_user.id)
    if not user_data:
        await update.message.reply_text(
            "No account found. Type /start to register! 😊"
        )
        return

    is_sub      = bool(user_data["subscribed"])
    user_filter = user_data["filters"] or "All"
    sub_icon    = "🟢" if is_sub else "🔴"
    sub_text    = "ACTIVE — you are receiving alerts" if is_sub else "INACTIVE — notifications are off"

    await update.message.reply_text(
        f"📊 *Your Account Status:*\n\n"
        f"{sub_icon} Subscription: {sub_text}\n"
        f"⚙️ Job Filter: *{user_filter}*\n"
        f"📅 Joined: {str(user_data['joined_at'])[:10]}\n\n"
        f"Tap ⚙️ *Job Filter* to change your preference.",
        parse_mode="Markdown",
        reply_markup=main_menu_inline(),
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    total_users = db.count_users()
    subscribed  = db.count_subscribed()
    total_jobs  = db.count_jobs()
    jobs_today  = db.count_jobs_today()
    sources     = db.count_by_source()

    source_lines = "\n".join(
        f"  {SOURCE_ICONS.get(s['source'], '•')} {s['source']}: {s['count']} jobs"
        for s in sources[:8]
    )

    await update.message.reply_text(
        f"📈 *Bot Statistics:*\n\n"
        f"👥 Total Users: *{total_users}*\n"
        f"🔔 Subscribed: *{subscribed}*\n"
        f"💼 Total Jobs Found: *{total_jobs}*\n"
        f"🆕 New Jobs Today: *{jobs_today}*\n\n"
        f"📡 *Jobs per Source:*\n{source_lines or '  No data yet'}",
        parse_mode="Markdown",
    )


async def delete_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """GDPR/privacy compliance — users can delete their data."""
    if update.effective_chat.type != "private":
        return
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes, delete my data", callback_data="confirm_delete"),
            InlineKeyboardButton("❌ Cancel",              callback_data="cancel_delete"),
        ]
    ])
    await update.message.reply_text(
        "⚠️ *Are you sure you want to delete your data?*\n\n"
        "This will remove:\n"
        "• Your subscription\n"
        "• Your job filter preference\n"
        "• All your stored information\n\n"
        "_This action cannot be undone._",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def scrape_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin only — force an immediate scrape."""
    user_id = update.effective_user.id
    if ADMIN_ID and user_id != ADMIN_ID:
        await update.message.reply_text("⛔ This command is for admins only.")
        return
    await update.message.reply_text("🔍 Starting manual scrape now...")
    await broadcast_new_jobs(context.bot)
    await update.message.reply_text("✅ Scraping complete!")


# ═══════════════════════════════════════════════════════════════════════════════
#  REPLY KEYBOARD BUTTON HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

async def reply_keyboard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text messages triggered by the persistent bottom keyboard buttons."""
    if update.effective_chat.type != "private":
        return

    text = update.message.text

    if text == BTN_HELP:
        await help_command(update, context)
    elif text == BTN_PRIVACY:
        await privacy_command(update, context)
    elif text == BTN_JOBS:
        await jobs_command(update, context)
    elif text == BTN_MENU:
        await update.message.reply_text(
            "🏠 *Main Menu:*",
            parse_mode="Markdown",
            reply_markup=main_menu_inline(),
        )
    elif text == BTN_SUB:
        await subscribe_command(update, context)
    elif text == BTN_FILTER:
        await filter_command(update, context)
    else:
        await update.message.reply_text(
            "I didn't understand that. 😅\n"
            "Use the buttons below or type /help to see all commands.",
            reply_markup=main_menu_inline(),
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  INLINE BUTTON CALLBACK HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data
    user  = query.from_user

    if data == "latest_jobs":
        user_data   = db.get_user(user.id)
        user_filter = user_data.get("filters", "All") if user_data else "All"
        await query.message.reply_text(
            "⏳ *Please wait, fetching the latest jobs...*",
            parse_mode="Markdown",
        )
        await send_latest_jobs(query.message.chat_id, context.bot, limit=15, category_filter=user_filter)

    elif data == "subscribe":
        db.add_user(user.id, user.first_name or "there")
        db.subscribe_user(user.id)
        await query.message.reply_text(
            "🔔 *You are now subscribed!*\n\n"
            "✅ You will be notified when new jobs are posted.\n"
            "⚙️ Use Job Filter to choose a specific job type.",
            parse_mode="Markdown",
        )

    elif data == "unsubscribe":
        db.unsubscribe_user(user.id)
        await query.message.reply_text(
            "🔕 *Alerts have been turned off.*\n"
            "Tap 🔔 Subscribe to turn them back on anytime.",
            parse_mode="Markdown",
        )

    elif data == "filter_menu":
        keyboard = [
            [InlineKeyboardButton("📋 All Jobs",                callback_data="filter_all")],
            [InlineKeyboardButton("📞 Call Center / BPO",       callback_data="filter_callcenter")],
            [InlineKeyboardButton("💻 Virtual Assistant (VA)",  callback_data="filter_va")],
            [InlineKeyboardButton("🎰 POGO / Online Gaming",    callback_data="filter_pogo")],
            [InlineKeyboardButton("🏠 Remote / Work From Home", callback_data="filter_remote")],
            [InlineKeyboardButton("💰 Accounting / Finance",    callback_data="filter_accounting")],
            [InlineKeyboardButton("🖥️ IT / Tech Support",       callback_data="filter_it")],
            [InlineKeyboardButton("📈 Sales / Marketing",       callback_data="filter_sales")],
            [InlineKeyboardButton("🏥 Healthcare / Nursing",    callback_data="filter_healthcare")],
        ]
        await query.message.reply_text(
            "⚙️ *Choose your preferred Job Type:*\n\n"
            "You will only receive notifications for the selected category.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("filter_"):
        filter_map = {
            "filter_all":        "All",
            "filter_callcenter": "Call Center / BPO",
            "filter_va":         "Virtual Assistant",
            "filter_pogo":       "POGO / Online Gaming",
            "filter_remote":     "Remote / WFH",
            "filter_accounting": "Accounting / Finance",
            "filter_it":         "IT / Tech",
            "filter_sales":      "Sales / Marketing",
            "filter_healthcare": "Healthcare",
        }
        chosen = filter_map.get(data, "All")
        db.add_user(user.id, user.first_name or "there")
        db.set_filter(user.id, chosen)
        icon = CATEGORY_ICONS.get(chosen, "💼")
        await query.message.reply_text(
            f"✅ *Filter set to:*\n{icon} *{chosen}*\n\n"
            f"You will now only receive *{chosen}* job notifications.",
            parse_mode="Markdown",
        )

    elif data == "my_status":
        user_data = db.get_user(user.id)
        if not user_data:
            await query.message.reply_text("Type /start first to register. 😊")
            return
        is_sub   = bool(user_data["subscribed"])
        sub_icon = "🟢" if is_sub else "🔴"
        sub_text = "ACTIVE" if is_sub else "INACTIVE"
        await query.message.reply_text(
            f"📊 *Your Status:*\n\n"
            f"{sub_icon} Subscription: *{sub_text}*\n"
            f"⚙️ Filter: *{user_data.get('filters', 'All')}*\n"
            f"📅 Joined: {str(user_data['joined_at'])[:10]}",
            parse_mode="Markdown",
        )

    elif data == "stats":
        total_users = db.count_users()
        subscribed  = db.count_subscribed()
        total_jobs  = db.count_jobs()
        jobs_today  = db.count_jobs_today()
        await query.message.reply_text(
            f"📈 *Bot Statistics:*\n\n"
            f"👥 Total Users: *{total_users}*\n"
            f"🔔 Subscribed: *{subscribed}*\n"
            f"💼 Total Jobs Found: *{total_jobs}*\n"
            f"🆕 New Jobs Today: *{jobs_today}*",
            parse_mode="Markdown",
        )

    elif data == "help":
        await query.message.reply_text(
            "❓ *Help*\n\n"
            "Use the menu buttons or type these commands:\n\n"
            "/jobs — Latest job postings\n"
            "/subscribe — Turn on alerts\n"
            "/unsubscribe — Turn off alerts\n"
            "/filter — Choose job type\n"
            "/status — View your settings\n"
            "/privacy — Terms & Privacy Policy\n"
            "/deletedata — Delete your data",
            parse_mode="Markdown",
            reply_markup=main_menu_inline(),
        )

    elif data == "privacy":
        await query.message.reply_text(
            PRIVACY_TEXT,
            parse_mode="Markdown",
            reply_markup=main_menu_inline(),
        )

    elif data == "confirm_delete":
        db.delete_user(user.id)
        await query.message.reply_text(
            "✅ *Your data has been deleted.*\n\n"
            "Thank you for using Job Scrapper PH!\n"
            "Type /start anytime if you want to use it again.",
            parse_mode="Markdown",
        )

    elif data == "cancel_delete":
        await query.message.reply_text(
            "❌ *Data deletion cancelled.*\n"
            "Your information is safe.",
            parse_mode="Markdown",
            reply_markup=main_menu_inline(),
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  JOB DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

async def send_latest_jobs(
    chat_id: int,
    bot,
    limit: int = 15,
    category_filter: str = "All",
    is_group: bool = False,
):
    if category_filter and category_filter != "All":
        jobs = db.get_latest_jobs_by_category(category=category_filter, limit=limit)
    else:
        jobs = db.get_latest_jobs(limit=limit)

    if not jobs:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "😔 *No jobs found at the moment.*\n\n"
                "Please wait — the bot checks for new postings every few minutes. "
                "Try again shortly! 🙏"
            ),
            parse_mode="Markdown",
        )
        return

    filter_text = f" ({category_filter})" if category_filter != "All" else ""
    await bot.send_message(
        chat_id=chat_id,
        text=f"💼 *{len(jobs)} Latest Jobs{filter_text}:*",
        parse_mode="Markdown",
    )

    for job in jobs:
        msg = format_job_message(job, is_group=is_group)
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=msg,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
            await asyncio.sleep(0.4)
        except Exception as e:
            logger.error(f"Error sending job to {chat_id}: {e}")


def format_job_message(job: dict, is_group: bool = False) -> str:
    category = job.get("category", "General")
    source   = job.get("source", "")
    icon     = CATEGORY_ICONS.get(category, "💼")
    src_icon = SOURCE_ICONS.get(source, "🌐")
    date_str = str(job.get("date_found", ""))[:16]
    salary   = f"\n💵 {job['salary']}" if job.get("salary") else ""

    msg = (
        f"{icon} *{job['title']}*\n"
        f"🏢 {job.get('company', 'Not specified')}\n"
        f"📂 {category}\n"
        f"📍 {job.get('location', 'Philippines')}"
        f"{salary}\n"
        f"{src_icon} {source} · 📅 {date_str}\n"
        f"🔗 [Apply here!]({job['link']})"
    )

    if is_group:
        msg += "\n\n⚠️ _Always verify the employer before applying. Never pay to get a job — that's a scam!_"

    return msg


# ═══════════════════════════════════════════════════════════════════════════════
#  BROADCAST — Personal Subscribers + Group
# ═══════════════════════════════════════════════════════════════════════════════

async def broadcast_new_jobs(bot):
    logger.info("🔍 Starting job scrape...")
    try:
        new_jobs = await scraper.scrape_all()
        logger.info(f"✅ Fetched {len(new_jobs)} potential jobs")
    except Exception as e:
        logger.error(f"Scraping error: {e}")
        return

    saved_jobs = []
    for job in new_jobs:
        if db.save_job(job):
            saved_jobs.append(job)

    logger.info(f"🆕 {len(saved_jobs)} new unique jobs saved")
    if not saved_jobs:
        logger.info("No new jobs found — nothing to broadcast.")
        return

    # ── 1. Post to GROUP (if GROUP_CHAT_ID is set) ─────────────────────────────
    if GROUP_CHAT_ID:
        try:
            total = len(saved_jobs)
            await bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=(
                    f"📢 *{total} NEW JOB POSTING{'S' if total > 1 else ''}!* 🇵🇭\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Here are the latest opportunities for you! 💪\n"
                    f"⚠️ _Always verify the employer's legitimacy. Never pay to get a job — that's a scam!_"
                ),
                parse_mode="Markdown",
            )
            for job in saved_jobs[:10]:
                await bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=format_job_message(job, is_group=True),
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
                await asyncio.sleep(0.5)

            if total > 10:
                await bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=f"➕ *{total - 10} more* new jobs available!\nMessage the bot directly to see all: /jobs",
                    parse_mode="Markdown",
                )
            logger.info(f"✅ Posted to group {GROUP_CHAT_ID}: {min(total, 10)} jobs")
        except Exception as e:
            logger.error(f"Group broadcast error: {e}")

    # ── 2. Send to individual SUBSCRIBERS ──────────────────────────────────────
    subscribers = db.get_subscribers()
    logger.info(f"📤 Sending to {len(subscribers)} personal subscribers")

    for user in subscribers:
        user_filter  = user.get("filters", "All")
        jobs_to_send = [
            j for j in saved_jobs
            if user_filter in ("All", "Lahat") or j.get("category") == user_filter
        ]
        if not jobs_to_send:
            continue

        try:
            total = len(jobs_to_send)
            await bot.send_message(
                chat_id=user["user_id"],
                text=(
                    f"🔔 *{total} NEW JOB POSTING{'S' if total > 1 else ''} FOR YOU!* 🇵🇭\n\n"
                    f"Here are the latest jobs. Don't miss out! 💪"
                ),
                parse_mode="Markdown",
            )
            for job in jobs_to_send[:5]:
                await bot.send_message(
                    chat_id=user["user_id"],
                    text=format_job_message(job),
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
                await asyncio.sleep(0.4)

            if total > 5:
                await bot.send_message(
                    chat_id=user["user_id"],
                    text=f"➕ *{total - 5} more* new jobs available! Type /jobs to see all.",
                    parse_mode="Markdown",
                )
        except Exception as e:
            logger.error(f"Broadcast error for {user['user_id']}: {e}")
            if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                db.unsubscribe_user(user["user_id"])


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN environment variable is not set!")

    db.init_db()
    logger.info("✅ Database initialized")

    if GROUP_CHAT_ID:
        logger.info(f"📢 Group posting enabled: {GROUP_CHAT_ID}")
    else:
        logger.info("ℹ️ No GROUP_CHAT_ID set — personal subscriber broadcast only.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",       start))
    app.add_handler(CommandHandler("help",        help_command))
    app.add_handler(CommandHandler("privacy",     privacy_command))
    app.add_handler(CommandHandler("jobs",        jobs_command))
    app.add_handler(CommandHandler("subscribe",   subscribe_command))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    app.add_handler(CommandHandler("filter",      filter_command))
    app.add_handler(CommandHandler("status",      status_command))
    app.add_handler(CommandHandler("stats",       stats_command))
    app.add_handler(CommandHandler("deletedata",  delete_data_command))
    app.add_handler(CommandHandler("scrapnow",    scrape_now_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        reply_keyboard_handler,
    ))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        broadcast_new_jobs,
        "interval",
        minutes=CHECK_INTERVAL_MINUTES,
        args=[app.bot],
        next_run_time=datetime.now(),
    )
    scheduler.start()
    logger.info(f"⏱ Scheduler started — checking every {CHECK_INTERVAL_MINUTES} minutes")

    logger.info("🤖 Job Scrapper PH is now running!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
