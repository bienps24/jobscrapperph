# 🤖 PH Job Hunter Bot

Telegram bot na naghahanap ng legit na trabaho sa Philippines — Call Center, VA, POGO, at Remote jobs.

---

## ✅ Features

- 🔍 Auto-scrape ng bagong jobs bawat 60 minuto (o base sa setting mo)
- 🔔 Real-time notification sa mga subscriber
- 📂 Filter by job type (Call Center, VA, POGO, Remote)
- 💾 SQLite database para walang duplicate na notifications
- 🌐 Multiple job sources: Indeed PH, JobStreet PH, OnlineJobs.ph, Jooble, Kalibrr

---

## 📁 Files

```
job-hunter-bot/
├── main.py          ← Main bot logic at commands
├── database.py      ← SQLite database operations
├── scraper.py       ← Job scrapers (multiple sources)
├── requirements.txt ← Python dependencies
├── Procfile         ← Para sa Railway deployment
├── railway.toml     ← Railway configuration
└── .env.example     ← Template ng environment variables
```

---

## 🚀 Deployment Guide (Railway)

### Step 1 — Gumawa ng Telegram Bot

1. Buksan ang Telegram
2. Hanapin si `@BotFather`
3. I-type: `/newbot`
4. Bigyan ng pangalan: `PH Job Hunter Bot`
5. Bigyan ng username: `phjobhunter_bot` (dapat unique)
6. **I-copy ang BOT TOKEN** — ganito ang format: `7123456789:AAHabcdefghijklmnopqrstuvwxyz`

---

### Step 2 — I-setup ang GitHub Repository

1. Pumunta sa [github.com](https://github.com) → New Repository
2. Pangalanan: `ph-job-hunter-bot`
3. I-clone sa computer mo:
   ```bash
   git clone https://github.com/YOUR_USERNAME/ph-job-hunter-bot.git
   cd ph-job-hunter-bot
   ```
4. I-copy lahat ng files dito sa folder
5. I-push sa GitHub:
   ```bash
   git add .
   git commit -m "Initial commit - PH Job Hunter Bot"
   git push origin main
   ```

---

### Step 3 — I-deploy sa Railway

1. Pumunta sa [railway.app](https://railway.app)
2. Sign in gamit ang GitHub account
3. Click **"New Project"**
4. Piliin **"Deploy from GitHub repo"**
5. Piliin ang `ph-job-hunter-bot` repo
6. I-click ang iyong project → **"Variables"** tab
7. I-add ang mga environment variables:

   | Variable | Value |
   |----------|-------|
   | `BOT_TOKEN` | `7123456789:AAHabcde...` (token mo mula kay BotFather) |
   | `CHECK_INTERVAL_MINUTES` | `60` |
   | `JOOBLE_API_KEY` | (optional — tingnan Step 4) |

8. Railway mag-a-auto-deploy! ✅

---

### Step 4 — (Optional) Jooble API Key para sa mas maraming jobs

1. Pumunta sa [jooble.org/api](https://jooble.org/api)
2. Mag-register ng libre
3. I-copy ang API key
4. I-add sa Railway variables: `JOOBLE_API_KEY=your_key_here`

> Kung walang Jooble API key, gagamit ang bot ng direct scraping — gumagana pa rin!

---

### Step 5 — I-test ang Bot

1. Buksan ang Telegram
2. Hanapin ang bot mo (sa username na pinili mo)
3. I-type `/start`
4. Dapat lumabas ang welcome message + buttons ✅

---

## ⚙️ Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Simulan ang bot, ipakita ang main menu |
| `/jobs` | Tingnan ang 10 pinakabagong jobs |
| `/subscribe` | Mag-subscribe sa job alerts |
| `/unsubscribe` | I-stop ang job alerts |
| `/filter` | I-set ang preferred job type |
| `/status` | Tingnan ang iyong subscription status |
| `/stats` | Bot statistics |
| `/help` | Ipakita ang lahat ng commands |

---

## 🔧 Local Testing (Optional)

Para ma-test sa sariling computer bago i-deploy:

```bash
# I-install ang dependencies
pip install -r requirements.txt

# Gumawa ng .env file
cp .env.example .env
# I-edit ang .env at ilagay ang BOT_TOKEN mo

# I-run ang bot
python main.py
```

---

## 📊 Job Sources

| Source | Job Types | Method |
|--------|-----------|--------|
| Indeed PH | Lahat | RSS Feed |
| JobStreet PH | Lahat | Web Scraping |
| OnlineJobs.ph | VA, Remote | Web Scraping |
| Jooble | Lahat | API / Scraping |
| Kalibrr | Lahat | Web Scraping |

---

## ❓ Troubleshooting

**Bot hindi nagre-respond:**
- I-check ang `BOT_TOKEN` sa Railway variables
- Tingnan ang logs sa Railway → "Deploy Logs"

**Walang jobs na lumalabas:**
- Normal lang sa unang ilang minuto
- Hintayin ang first scraping cycle (base sa `CHECK_INTERVAL_MINUTES`)
- I-check ang Railway logs para sa error messages

**Railway deployment failed:**
- I-check kung kumpleto ang lahat ng files
- Siguraduhing may `Procfile` at `requirements.txt`

---

## 📝 Notes

- Ang database (`jobs.db`) ay nire-reset kapag nag-redeploy sa Railway. Para permanent ang data, pwede mag-upgrade sa Railway's PostgreSQL add-on.
- Ang bot ay automatic na nag-a-unsubscribe sa mga user na nag-block na ng bot.
- Max 5 jobs per broadcast notification para hindi spam.
