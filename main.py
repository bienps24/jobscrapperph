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
BOT_TOKEN               = os.environ.get("BOT_TOKEN", "")
CHECK_INTERVAL_MINUTES  = int(os.environ.get("CHECK_INTERVAL_MINUTES", "60"))
ADMIN_ID                = int(os.environ.get("ADMIN_ID", "0"))
# Group/Channel ID kung saan mag-popost ng jobs (optional)
# Example: -1001234567890  ← dapat negative number para sa groups
GROUP_CHAT_ID           = os.environ.get("GROUP_CHAT_ID", "")

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
    "RemoteOK":      "🔸",
}

# Trigger words para sa reply keyboard (hindi commands, text buttons siya)
BTN_HELP     = "❓ Help"
BTN_PRIVACY  = "📋 Terms & Privacy"
BTN_JOBS     = "🔍 Pinakabagong Jobs"
BTN_MENU     = "🏠 Menu"
BTN_SUB      = "🔔 Subscribe"
BTN_FILTER   = "⚙️ Job Filter"


# ═══════════════════════════════════════════════════════════════════════════════
#  KEYBOARDS
# ═══════════════════════════════════════════════════════════════════════════════

def bottom_keyboard():
    """
    Persistent na keyboard sa baba ng chat — laging visible sa personal messages.
    Ito yung katulad ng screenshot mo: Help + Terms & Privacy buttons sa pinakababa.
    Hindi ito lalabas sa group posts — para sa private chat lang.
    """
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_JOBS), KeyboardButton(BTN_SUB)],
            [KeyboardButton(BTN_FILTER), KeyboardButton(BTN_MENU)],
            [KeyboardButton(BTN_HELP), KeyboardButton(BTN_PRIVACY)],
        ],
        resize_keyboard=True,       # mas maliit at maganda
        is_persistent=True,         # hindi disappear kahit mag-type
        input_field_placeholder="Piliin ang aksyon o mag-type ng command...",
    )


def main_menu_inline():
    """Inline buttons sa loob ng message — para sa main menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Pinakabagong Jobs",   callback_data="latest_jobs")],
        [
            InlineKeyboardButton("🔔 Mag-Subscribe",   callback_data="subscribe"),
            InlineKeyboardButton("🔕 I-stop Alerts",   callback_data="unsubscribe"),
        ],
        [InlineKeyboardButton("⚙️ Piliin ang Job Type", callback_data="filter_menu")],
        [
            InlineKeyboardButton("📊 Aking Status",    callback_data="my_status"),
            InlineKeyboardButton("📈 Bot Stats",       callback_data="stats"),
        ],
        [
            InlineKeyboardButton("❓ Help",            callback_data="help"),
            InlineKeyboardButton("📋 Terms & Privacy", callback_data="privacy"),
        ],
    ])


# ═══════════════════════════════════════════════════════════════════════════════
#  PRIVACY & TERMS TEXT
# ═══════════════════════════════════════════════════════════════════════════════

PRIVACY_TEXT = """
📋 *Terms of Service at Privacy Policy*
━━━━━━━━━━━━━━━━━━━━━━

🤖 *Tungkol sa Bot Na Ito*
Ang *PH Job Finder Bot* ay isang automated na serbisyo na nag-co-collect ng mga publikong job postings mula sa iba't ibang websites para sa kaginhawahan ng mga naghahanap ng trabaho.

━━━━━━━━━━━━━━━━━━━━━━
📌 *Mga Tuntunin ng Paggamit*

✅ *Pinapayagan:*
• Gamitin para sa personal na paghahanap ng trabaho
• I-share ang mga job listings sa mga kaibigan at pamilya
• Mag-subscribe at mag-filter ng trabaho

❌ *Hindi Pinapayagan:*
• Gumamit ng bot para sa spam o scam
• Mag-post ng pekeng job listings
• Gamitin para sa anumang illegal na layunin
• Mag-scrape ng data ng bot para sa sariling bentahe

━━━━━━━━━━━━━━━━━━━━━━
🔒 *Privacy at Data*

• Kinokolekta namin ang iyong *Telegram User ID* at *pangalan* para mapadala ang job notifications.
• *Hindi namin ibinibigay* ang iyong personal na impormasyon sa kahit sino.
• *Hindi namin nino-noto* ang iyong mga mensahe o aktibidad sa labas ng bot.
• Maaari mong i-request ang pagbura ng iyong data anumang oras sa pamamagitan ng /deletedata.
• Ang iyong subscription at filter preferences ay naka-store sa aming database.

━━━━━━━━━━━━━━━━━━━━━━
⚠️ *Disclaimer*

• Ang bot na ito ay *hindi* nagga-garantiya ng katumpakan ng mga job listings.
• Lahat ng job postings ay galing sa *panlabas na websites* — hindi kami ang employer.
• *Palaging i-verify* ang legitimacy ng employer bago mag-apply.
• Maging maingat sa mga nagtatanong ng *bayad para sa trabaho* — scam yan!

━━━━━━━━━━━━━━━━━━━━━━
📞 *Para sa Katanungan*
Makipag-ugnayan sa admin ng bot kung may concerns ka.

_Ang patuloy na paggamit ng bot ay nangangahulugang sumasang-ayon ka sa mga tuntunin na ito._
""".strip()


# ═══════════════════════════════════════════════════════════════════════════════
#  COMMANDS — PRIVATE CHAT ONLY
# ═══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Huwag mag-respond sa /start sa group
    if update.effective_chat.type != "private":
        return

    user    = update.effective_user
    is_new  = db.add_user(user.id, user.first_name or "Kabayan")
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
        "📲 *Gamitin ang mga button sa baba para magsimula!* 👇"
    )

    # Ipadala ang welcome + inline menu + persistent bottom keyboard
    await update.message.reply_text(
        welcome,
        parse_mode="Markdown",
        reply_markup=bottom_keyboard(),   # ← ito ang persistent sa baba
    )
    # Sundan ng inline menu
    await update.message.reply_text(
        "🏠 *Pangunahing Menu:*",
        parse_mode="Markdown",
        reply_markup=main_menu_inline(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Huwag mag-respond sa group
    if update.effective_chat.type != "private":
        return

    text = (
        "❓ *Tulong / Help*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📱 *Mga Available na Commands:*\n\n"
        "/start — Pangunahing menu\n"
        "/jobs — Pinakabagong 15 job posts\n"
        "/subscribe — Mag-on ng job alerts\n"
        "/unsubscribe — Mag-off ng notifications\n"
        "/filter — Piliin ang klase ng trabaho\n"
        "/status — Tingnan ang iyong settings\n"
        "/stats — Mga bilang at statistics\n"
        "/privacy — Terms at Privacy Policy\n"
        "/deletedata — Burahin ang iyong data\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔔 *Paano gumagana ang bot?*\n\n"
        "1️⃣ I-tap ang 🔔 *Subscribe* button\n"
        "2️⃣ Piliin ang gusto mong *job type* sa Filter\n"
        "3️⃣ Aabisuhan ka ng bot kapag may *bagong posting*!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⏱ *Gaano kadalas mag-update?*\n"
        f"Bawat *{CHECK_INTERVAL_MINUTES} minuto* nag-che-check ang bot ng bagong jobs.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 *Mga Tips:*\n"
        "• Mag-filter ng specific job type para mas relevant ang notifications\n"
        "• Maging maingat sa mga employer na nagtatanong ng bayad — scam yan!\n"
        "• I-verify palagi ang legitimacy ng company bago mag-apply\n\n"
        "🆘 Kung may problema o tanong, makipag-ugnayan sa admin."
    )
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu_inline(),
    )


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Huwag mag-respond sa group
    if update.effective_chat.type != "private":
        return

    await update.message.reply_text(
        PRIVACY_TEXT,
        parse_mode="Markdown",
        reply_markup=main_menu_inline(),
    )


async def jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Sa group: walang filter, mag-post lang ng latest
    is_private = update.effective_chat.type == "private"
    if is_private:
        user_data   = db.get_user(update.effective_user.id)
        user_filter = user_data.get("filters", "Lahat") if user_data else "Lahat"
    else:
        user_filter = "Lahat"

    await update.message.reply_text(
        "⏳ *Sandali lang, hinahanap ko ang mga jobs...*",
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
            "💬 Para mag-subscribe ng personal job alerts, mag-message sa akin directly!\n"
            "I-click ang aking username para mag-private message. 😊"
        )
        return

    user = update.effective_user
    db.add_user(user.id, user.first_name or "Kabayan")
    db.subscribe_user(user.id)
    await update.message.reply_text(
        "🔔 *Naka-subscribe ka na!*\n\n"
        "✅ Aabisuhan kita tuwing may bagong job posting.\n"
        "⚙️ I-tap ang *Job Filter* para piliin ang specific na trabaho.\n"
        "🔕 I-tap ang *I-stop Alerts* para ihinto.",
        parse_mode="Markdown",
        reply_markup=main_menu_inline(),
    )


async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    db.unsubscribe_user(update.effective_user.id)
    await update.message.reply_text(
        "🔕 *Na-off na ang iyong job alerts.*\n\n"
        "Hindi ka na makakatanggap ng notifications.\n"
        "I-tap ang 🔔 *Subscribe* para bumalik anumang oras! 😊",
        parse_mode="Markdown",
        reply_markup=main_menu_inline(),
    )


async def filter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    keyboard = [
        [InlineKeyboardButton("📋 Lahat ng Trabaho",      callback_data="filter_all")],
        [InlineKeyboardButton("📞 Call Center / BPO",     callback_data="filter_callcenter")],
        [InlineKeyboardButton("💻 Virtual Assistant (VA)", callback_data="filter_va")],
        [InlineKeyboardButton("🎰 POGO / Online Gaming",  callback_data="filter_pogo")],
        [InlineKeyboardButton("🏠 Remote / Work From Home", callback_data="filter_remote")],
        [InlineKeyboardButton("💰 Accounting / Finance",  callback_data="filter_accounting")],
        [InlineKeyboardButton("🖥️ IT / Tech Support",     callback_data="filter_it")],
        [InlineKeyboardButton("📈 Sales / Marketing",     callback_data="filter_sales")],
        [InlineKeyboardButton("🏥 Healthcare / Nursing",  callback_data="filter_healthcare")],
    ]
    await update.message.reply_text(
        "⚙️ *Piliin ang Job Type na gusto mo:*\n\n"
        "Matatanggap mo lang ang notifications para sa napiling klase ng trabaho.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    user_data = db.get_user(update.effective_user.id)
    if not user_data:
        await update.message.reply_text(
            "Wala pa akong record sa iyo. I-type /start para magsimula! 😊"
        )
        return

    is_sub     = bool(user_data["subscribed"])
    user_filter = user_data["filters"] or "Lahat"
    sub_icon   = "🟢" if is_sub else "🔴"
    sub_text   = "AKTIBO — tumatanggap ka ng alerts" if is_sub else "HINDI AKTIBO"

    await update.message.reply_text(
        f"📊 *Iyong Account Status:*\n\n"
        f"{sub_icon} Subscription: {sub_text}\n"
        f"⚙️ Job Filter: *{user_filter}*\n"
        f"📅 Sumali noong: {str(user_data['joined_at'])[:10]}\n\n"
        f"I-tap ang ⚙️ *Job Filter* para baguhin ang preference.",
        parse_mode="Markdown",
        reply_markup=main_menu_inline(),
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    total_users  = db.count_users()
    subscribed   = db.count_subscribed()
    total_jobs   = db.count_jobs()
    jobs_today   = db.count_jobs_today()
    sources      = db.count_by_source()

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


async def delete_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Para sa GDPR/privacy compliance — users can delete their data."""
    if update.effective_chat.type != "private":
        return
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Oo, burahin ang aking data", callback_data="confirm_delete"),
            InlineKeyboardButton("❌ Hindi, i-cancel",            callback_data="cancel_delete"),
        ]
    ])
    await update.message.reply_text(
        "⚠️ *Sigurado ka bang gusto mong burahin ang iyong data?*\n\n"
        "Mabubura ang:\n"
        "• Iyong subscription\n"
        "• Job filter preference\n"
        "• Lahat ng iyong stored na impormasyon\n\n"
        "_Hindi na ito mababawi._",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def scrape_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin only — force scrape now."""
    user_id = update.effective_user.id
    if ADMIN_ID and user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only ang command na ito.")
        return
    await update.message.reply_text("🔍 Sisimulan ko ang manual scraping ngayon...")
    await broadcast_new_jobs(context.bot)
    await update.message.reply_text("✅ Tapos na ang scraping!")


# ═══════════════════════════════════════════════════════════════════════════════
#  REPLY KEYBOARD BUTTON HANDLER
#  (Ginagawa itong text message handler para sa bottom keyboard buttons)
# ═══════════════════════════════════════════════════════════════════════════════

async def reply_keyboard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles ang mga text na galing sa persistent bottom keyboard buttons."""
    # Sa group chat, huwag pansinin ang mga text na ito
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
        # Ipakita ang inline main menu
        await update.message.reply_text(
            "🏠 *Pangunahing Menu:*",
            parse_mode="Markdown",
            reply_markup=main_menu_inline(),
        )
    elif text == BTN_SUB:
        await subscribe_command(update, context)
    elif text == BTN_FILTER:
        await filter_command(update, context)
    else:
        # Unknown text
        await update.message.reply_text(
            "Hindi ko maintindihan yun. 😅 Gamitin ang mga button sa baba o i-type /help.",
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
        user_filter = user_data.get("filters", "Lahat") if user_data else "Lahat"
        await query.message.reply_text(
            "⏳ *Sandali lang, hinahanap ko ang mga jobs...*", parse_mode="Markdown"
        )
        await send_latest_jobs(query.message.chat_id, context.bot, limit=15, category_filter=user_filter)

    elif data == "subscribe":
        db.add_user(user.id, user.first_name or "Kabayan")
        db.subscribe_user(user.id)
        await query.message.reply_text(
            "🔔 *Naka-subscribe ka na!*\n\n"
            "✅ Aabisuhan kita ng bagong job posts.\n"
            "⚙️ I-tap ang Job Filter para piliin ang specific na trabaho.",
            parse_mode="Markdown",
        )

    elif data == "unsubscribe":
        db.unsubscribe_user(user.id)
        await query.message.reply_text(
            "🔕 *Na-off na ang iyong alerts.*\n"
            "I-tap ang 🔔 Subscribe para bumalik anumang oras.",
            parse_mode="Markdown",
        )

    elif data == "filter_menu":
        keyboard = [
            [InlineKeyboardButton("📋 Lahat ng Trabaho",       callback_data="filter_all")],
            [InlineKeyboardButton("📞 Call Center / BPO",      callback_data="filter_callcenter")],
            [InlineKeyboardButton("💻 Virtual Assistant (VA)",  callback_data="filter_va")],
            [InlineKeyboardButton("🎰 POGO / Online Gaming",   callback_data="filter_pogo")],
            [InlineKeyboardButton("🏠 Remote / Work From Home", callback_data="filter_remote")],
            [InlineKeyboardButton("💰 Accounting / Finance",   callback_data="filter_accounting")],
            [InlineKeyboardButton("🖥️ IT / Tech Support",      callback_data="filter_it")],
            [InlineKeyboardButton("📈 Sales / Marketing",      callback_data="filter_sales")],
            [InlineKeyboardButton("🏥 Healthcare / Nursing",   callback_data="filter_healthcare")],
        ]
        await query.message.reply_text(
            "⚙️ *Piliin ang Job Type na gusto mo:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("filter_"):
        filter_map = {
            "filter_all":        "Lahat",
            "filter_callcenter": "Call Center / BPO",
            "filter_va":         "Virtual Assistant",
            "filter_pogo":       "POGO / Online Gaming",
            "filter_remote":     "Remote / WFH",
            "filter_accounting": "Accounting / Finance",
            "filter_it":         "IT / Tech",
            "filter_sales":      "Sales / Marketing",
            "filter_healthcare": "Healthcare",
        }
        chosen = filter_map.get(data, "Lahat")
        db.add_user(user.id, user.first_name or "Kabayan")
        db.set_filter(user.id, chosen)
        icon = CATEGORY_ICONS.get(chosen, "💼")
        await query.message.reply_text(
            f"✅ *Na-set ang filter mo sa:*\n{icon} *{chosen}*\n\n"
            f"Mga {chosen} jobs lang ang ipapakita sa iyo.",
            parse_mode="Markdown",
        )

    elif data == "my_status":
        user_data = db.get_user(user.id)
        if not user_data:
            await query.message.reply_text("I-type /start muna para mag-register. 😊")
            return
        is_sub    = bool(user_data["subscribed"])
        sub_icon  = "🟢" if is_sub else "🔴"
        sub_text  = "AKTIBO" if is_sub else "HINDI AKTIBO"
        await query.message.reply_text(
            f"📊 *Iyong Status:*\n\n"
            f"{sub_icon} Subscription: *{sub_text}*\n"
            f"⚙️ Filter: *{user_data.get('filters', 'Lahat')}*\n"
            f"📅 Sumali: {str(user_data['joined_at'])[:10]}",
            parse_mode="Markdown",
        )

    elif data == "stats":
        total_users = db.count_users()
        subscribed  = db.count_subscribed()
        total_jobs  = db.count_jobs()
        jobs_today  = db.count_jobs_today()
        await query.message.reply_text(
            f"📈 *Bot Statistics:*\n\n"
            f"👥 Kabuuang Users: *{total_users}*\n"
            f"🔔 Naka-subscribe: *{subscribed}*\n"
            f"💼 Kabuuang Jobs na Nakita: *{total_jobs}*\n"
            f"🆕 Bagong Jobs Ngayon: *{jobs_today}*",
            parse_mode="Markdown",
        )

    elif data == "help":
        await query.message.reply_text(
            "❓ *Tulong / Help*\n\n"
            "Gamitin ang mga button sa menu o i-type ang mga commands:\n\n"
            "/jobs — Pinakabagong jobs\n"
            "/subscribe — Mag-on ng alerts\n"
            "/unsubscribe — Mag-off ng alerts\n"
            "/filter — Piliin ang job type\n"
            "/status — Tingnan ang settings\n"
            "/privacy — Terms at Privacy\n"
            "/deletedata — Burahin ang iyong data",
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
            "✅ *Nabura na ang iyong data.*\n\n"
            "Salamat sa paggamit ng PH Job Finder Bot!\n"
            "I-type /start para magsimula ulit kung gusto mo.",
            parse_mode="Markdown",
        )

    elif data == "cancel_delete":
        await query.message.reply_text(
            "❌ *Na-cancel ang pagbura ng data.*\n"
            "Ang iyong impormasyon ay ligtas pa rin.",
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
    category_filter: str = "Lahat",
    is_group: bool = False,
):
    if category_filter and category_filter != "Lahat":
        jobs = db.get_latest_jobs_by_category(category=category_filter, limit=limit)
    else:
        jobs = db.get_latest_jobs(limit=limit)

    if not jobs:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "😔 *Wala pang nakuhang jobs sa ngayon.*\n\n"
                "Mag-antay sandali — bawat ilang minuto ay nag-che-check ang bot. 🙏"
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
        f"🏢 {job.get('company', 'Hindi nabanggit')}\n"
        f"📂 {category}\n"
        f"📍 {job.get('location', 'Philippines')}"
        f"{salary}\n"
        f"{src_icon} {source} · 📅 {date_str}\n"
        f"🔗 [I-apply dito!]({job['link']})"
    )

    # Sa group post, dagdag ng reminder para sa safety
    if is_group:
        msg += "\n\n⚠️ _Palaging i-verify ang employer bago mag-apply. Maging maingat sa scam!_"

    return msg


# ═══════════════════════════════════════════════════════════════════════════════
#  BROADCAST — Personal Subscribers + Group
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

    # ── 1. Mag-post sa GROUP (kung may GROUP_CHAT_ID) ──────────────────────────
    if GROUP_CHAT_ID:
        try:
            total = len(saved_jobs)
            await bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=(
                    f"📢 *{total} BAGONG JOB POSTING{'S' if total > 1 else ''}!* 🇵🇭\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Narito ang mga pinakabago para sa inyo, mga Kabayan! 💪\n"
                    f"⚠️ _Palaging i-verify ang legitimacy ng employer. Huwag magbayad para sa trabaho — scam yan!_"
                ),
                parse_mode="Markdown",
            )
            for job in saved_jobs[:10]:  # max 10 sa group para hindi spam
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
                    text=f"➕ At *{total - 10} pa* na bagong jobs!\nMag-PM sa bot para makita lahat: /jobs",
                    parse_mode="Markdown",
                )
            logger.info(f"✅ Naka-post sa group {GROUP_CHAT_ID}: {min(total, 10)} jobs")
        except Exception as e:
            logger.error(f"Group broadcast error: {e}")

    # ── 2. Mag-send sa individual SUBSCRIBERS ─────────────────────────────────
    subscribers = db.get_subscribers()
    logger.info(f"📤 Magse-send sa {len(subscribers)} personal subscribers")

    for user in subscribers:
        user_filter  = user.get("filters", "Lahat")
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
                    f"🔔 *{total} BAGONG JOB POSTING{'S' if total > 1 else ''} PARA SA IYO!* 🇵🇭\n\n"
                    f"Narito ang pinakabago. Huwag palampasin! 💪"
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
                    text=f"➕ At *{total - 5} pa* na bagong jobs! I-type /jobs para makita lahat.",
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
        logger.info("ℹ️ Walang GROUP_CHAT_ID — personal subscriber broadcast lang ang gagana.")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start",        start))
    app.add_handler(CommandHandler("help",         help_command))
    app.add_handler(CommandHandler("privacy",      privacy_command))
    app.add_handler(CommandHandler("jobs",         jobs_command))
    app.add_handler(CommandHandler("subscribe",    subscribe_command))
    app.add_handler(CommandHandler("unsubscribe",  unsubscribe_command))
    app.add_handler(CommandHandler("filter",       filter_command))
    app.add_handler(CommandHandler("status",       status_command))
    app.add_handler(CommandHandler("stats",        stats_command))
    app.add_handler(CommandHandler("deletedata",   delete_data_command))
    app.add_handler(CommandHandler("scrapnow",     scrape_now_command))

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(button_handler))

    # Persistent reply keyboard button handler (text messages sa private chat)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        reply_keyboard_handler,
    ))

    # Scheduler
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
