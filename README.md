# 🤖 PH Job Finder Bot 🇵🇭

Telegram bot para sa mga Pilipinong naghahanap ng trabaho.
Auto-scrape ng **legit at updated** na job postings bawat oras!

---

## ✅ Mga Features

- 🔍 Auto-scrape ng bagong jobs bawat **60 minuto**
- 🔔 Real-time Telegram notification sa mga subscriber
- 📂 **8 job categories** na mapipili
- 🌐 **10 job sources** — pinakamarami sa lahat!
- 💾 SQLite database — walang duplicate notifications
- 🇵🇭 Full **Tagalog/Taglish** na interface
- 💰 Ipinapakita ang **salary range** kung available
- 👤 Admin command para sa manual scraping (`/scrapnow`)

---

## 🌐 Mga Pinagkukuhaan ng Jobs (10 Sources)

| # | Source | Uri | Paraan |
|---|--------|-----|--------|
| 1 | **Indeed PH** | Lahat | RSS Feed ✅ |
| 2 | **JobStreet PH** | Lahat | Web Scrape + JSON-LD |
| 3 | **OnlineJobs.ph** | VA, Remote | Web Scrape |
| 4 | **Jooble** | Lahat | API + Web Scrape |
| 5 | **Kalibrr** | Lahat | JSON-LD + Web Scrape |
| 6 | **LinkedIn PH** | Lahat | Public Search |
| 7 | **Trabaho.ph** | Lahat | Web Scrape |
| 8 | **BossJob PH** | Lahat | JSON-LD + Web Scrape |
| 9 | **PhilJobNet (DOLE)** | Lahat | RSS + Web Scrape |
| 10 | **RemoteOK** | Remote | JSON API ✅ |

---

## 💼 Mga Job Categories

- 📞 Call Center / BPO
- 💻 Virtual Assistant (VA)
- 🎰 POGO / Online Gaming
- 🏠 Remote / Work From Home
- 💰 Accounting / Finance
- 🖥️ IT / Tech Support
- 📈 Sales / Marketing
- 🏥 Healthcare / Nursing

---

## 🚀 Paano I-deploy sa Railway (Step-by-Step)

### Step 1 — Gumawa ng Telegram Bot

1. Buksan ang Telegram, hanapin si `@BotFather`
2. I-type: `/newbot`
3. Bigyan ng **pangalan**: `PH Job Finder Bot`
4. Bigyan ng **username**: `phjobfinderph_bot` *(dapat may "bot" sa dulo, at unique)*
5. **I-copy ang BOT TOKEN** — ganito ang format:
   ```
   7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
6. Para mahanap ang iyong **Admin ID** (para sa `/scrapnow` command):
   - Hanapin si `@userinfobot` sa Telegram
   - I-type `/start` — ibibigay niya ang iyong Telegram ID

---

### Step 2 — I-upload sa GitHub

1. Pumunta sa [github.com](https://github.com) → **New Repository**
2. Pangalanan: `ph-job-finder-bot` (private or public, pareho okay)
3. I-upload ang lahat ng files:
   ```
   main.py
   database.py
   scraper.py
   requirements.txt
   Procfile
   railway.toml
   .gitignore
   README.md
   ```
   *(HUWAG i-upload ang `.env` file — secret yun!)*

4. Sa GitHub website, click **"uploading an existing file"** para mag-drag-and-drop

---

### Step 3 — I-deploy sa Railway

1. Pumunta sa [railway.app](https://railway.app)
2. Mag-sign in gamit ang **GitHub account**
3. Click **"New Project"** → **"Deploy from GitHub repo"**
4. Piliin ang `ph-job-finder-bot` repo
5. Hintayin ang initial deployment (may error muna — normal, wala pang token)
6. Click ang iyong project → tab na **"Variables"**
7. I-add ang mga ito:

   | Variable Name | Value | Required? |
   |---------------|-------|-----------|
   | `BOT_TOKEN` | `7123456789:AAH...` | ✅ REQUIRED |
   | `CHECK_INTERVAL_MINUTES` | `60` | Optional |
   | `ADMIN_ID` | `123456789` | Optional |
   | `JOOBLE_API_KEY` | *(kuha sa jooble.org/api — libre)* | Optional |

8. Pagkatapos mag-add ng variables → Railway mag-re-redeploy automatically
9. Tingnan ang **"Logs"** tab — dapat makita mo:
   ```
   ✅ Database initialized
   🤖 PH Job Finder Bot ay tumatakbo na!
   ```

---

### Step 4 — I-test ang Bot

1. Buksan ang Telegram
2. Hanapin ang bot mo gamit ang username na pinili
3. I-type `/start`
4. Dapat lumabas ang welcome message na may mga buttons ✅

---

### Step 5 — (Optional) Libre na Jooble API Key

1. Pumunta sa [jooble.org/api](https://jooble.org/api)
2. Mag-fill ng form (libre)
3. Makakakuha ng API key sa email
4. I-add sa Railway Variables: `JOOBLE_API_KEY=your_key_here`
5. Magdadagdag ito ng mas maraming job results!

---

## ⚙️ Mga Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Pangunahing menu ng bot |
| `/jobs` | Pinakabagong 15 jobs (base sa iyong filter) |
| `/subscribe` | I-on ang job alert notifications |
| `/unsubscribe` | I-off ang notifications |
| `/filter` | Piliin ang job type preference |
| `/status` | Tingnan ang iyong settings |
| `/stats` | Bot statistics at source breakdown |
| `/scrapnow` | *(Admin only)* Manual scraping agad |
| `/help` | Listahan ng lahat ng commands |

---

## 📁 Mga Files

```
ph-job-finder-bot/
├── main.py          ← Bot logic, commands, buttons, broadcast
├── database.py      ← SQLite operations (users + jobs)
├── scraper.py       ← 10 job site scrapers
├── requirements.txt ← Python packages
├── Procfile         ← Railway start command
├── railway.toml     ← Railway configuration
├── .gitignore       ← Mga hindi dapat i-upload sa GitHub
└── README.md        ← Itong guide na ito
```

---

## ❓ Troubleshooting

**"Bot hindi nagre-respond"**
- I-check ang `BOT_TOKEN` sa Railway Variables tab
- Tingnan ang Railway → Deployments → Logs

**"Walang jobs na lumalabas"**
- Normal sa unang 1-2 minuto
- Gamitin ang `/scrapnow` (kung may ADMIN_ID ka) para mag-force scrape
- O hintayin ang unang automatic cycle

**"Railway deployment failed"**
- Siguraduhing lahat ng files ay na-upload sa GitHub
- I-check kung may `Procfile` at `requirements.txt`

**"LinkedIn/JobStreet walang results"**
- Minsan nag-ba-block ng scraper ang mga sites
- Normal lang — ang ibang sources ay patuloy na gumagana

---

## 📝 Importanteng Notes

- ⚠️ Ang `jobs.db` ay nire-reset sa Railway kapag nag-redeploy. Para permanent ang data, upgrade sa Railway's **PostgreSQL** add-on.
- 🔒 Huwag ever i-commit ang `.env` file sa GitHub.
- 📊 Max 5 jobs per broadcast notification para hindi mag-mukhang spam.
- 🚫 Ang bot ay auto-unsubscribe sa mga user na nag-block ng bot.
