"""
Job Scrapper PH — Rebuilt for Reliability
==========================================
Priority: RSS Feeds & APIs first (most stable), Web Scraping as fallback.

Sources:
  1.  Indeed PH          ✅ RSS Feed       — Very reliable
  2.  RemoteOK           ✅ JSON API       — Very reliable
  3.  Jooble             ✅ API / Scrape   — Reliable
  4.  PhilJobNet (DOLE)  ✅ RSS Feed       — Reliable
  5.  LinkedIn PH        ⚠️  Web Scrape    — Works but may vary
  6.  JobStreet PH       ⚠️  Web Scrape    — Has bot protection
  7.  OnlineJobs.ph      ⚠️  Web Scrape    — Moderate reliability
  8.  Kalibrr            ⚠️  Web Scrape    — Has bot protection
  9.  BossJob PH         ⚠️  Web Scrape    — Moderate reliability
  10. Trabaho.ph         ⚠️  Web Scrape    — Moderate reliability

Strategy:
  - Each scraper has a timeout + try/except so one failure never blocks others
  - All scrapers run CONCURRENTLY (faster)
  - Results are deduplicated by URL
  - Logging shows exactly how many jobs each source returned
"""

import asyncio
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from typing import List, Dict

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ─── Rotate User Agents to avoid bot detection ────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

_ua_index = 0

def get_headers(extra: dict = None) -> dict:
    global _ua_index
    _ua_index = (_ua_index + 1) % len(USER_AGENTS)
    h = {
        "User-Agent": USER_AGENTS[_ua_index],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    if extra:
        h.update(extra)
    return h


TIMEOUT = 15  # seconds per request

# ═══════════════════════════════════════════════════════════════════════════════
#  KEYWORDS & CATEGORY DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

KEYWORDS = {
    "Call Center / BPO": [
        "call center", "callcenter", "customer service", "customer support",
        "BPO", "CSR", "contact center", "helpdesk", "help desk",
        "inbound", "outbound", "collections agent", "telemarketer",
        "technical support", "tier 1", "tier 2", "voice agent",
        "non-voice", "chat support", "email support",
    ],
    "Virtual Assistant": [
        "virtual assistant", "VA", "admin assistant", "administrative assistant",
        "data entry", "online assistant", "remote assistant", "executive assistant",
        "social media manager", "content moderator", "online tutor",
        "bookkeeper", "transcriptionist", "research assistant",
        "project coordinator", "operations assistant",
    ],
    "POGO / Online Gaming": [
        "POGO", "online gaming", "gaming operator", "casino dealer",
        "live dealer", "casino staff", "igaming", "i-gaming",
        "online casino", "gaming company", "esports", "game master",
        "casino host", "poker dealer",
    ],
    "Remote / WFH": [
        "work from home", "WFH", "remote work", "remote job", "telecommute",
        "home based", "homebased", "online job", "freelance", "flexible work",
        "hybrid work", "remote first",
    ],
    "Accounting / Finance": [
        "accountant", "accounting", "bookkeeper", "bookkeeping", "auditor",
        "finance officer", "payroll", "CPA", "accounts payable",
        "accounts receivable", "financial analyst", "treasury",
    ],
    "IT / Tech": [
        "software developer", "web developer", "programmer", "IT support",
        "network engineer", "system administrator", "devops", "QA engineer",
        "data analyst", "data scientist", "UI UX", "frontend", "backend",
        "full stack", "mobile developer", "cybersecurity",
    ],
    "Sales / Marketing": [
        "sales representative", "sales agent", "marketing officer",
        "digital marketing", "SEO specialist", "content writer",
        "copywriter", "graphic designer", "social media", "brand ambassador",
        "account manager", "business development",
    ],
    "Healthcare": [
        "nurse", "nursing", "caregiver", "medical", "healthcare",
        "pharmacist", "physical therapist", "radiologist", "midwife",
        "dental", "optometrist", "medical coder", "medical transcriptionist",
    ],
}

ALL_KEYWORDS = [kw for kws in KEYWORDS.values() for kw in kws]


def detect_category(title: str, description: str = "") -> str:
    text = (title + " " + description).lower()
    for category, keywords in KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                return category
    return "General"


def is_relevant(title: str, description: str = "") -> bool:
    text = (title + " " + description).lower()
    return any(kw.lower() in text for kw in ALL_KEYWORDS)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def make_job(title, company, link, source, location="Philippines", salary=None, description="") -> Dict:
    return {
        "title":    clean(title),
        "company":  clean(company) or "Not specified",
        "link":     (link or "").strip(),
        "category": detect_category(title, description),
        "location": clean(location) or "Philippines",
        "salary":   clean(salary) if salary else None,
        "source":   source,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN SCRAPER CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class JobScraper:

    async def scrape_all(self) -> List[Dict]:
        """Run all scrapers concurrently and return deduplicated relevant jobs."""

        # List of (scraper_function, source_name)
        scrapers = [
            # ── TIER 1: RSS Feeds & APIs (most reliable) ──────────────────────
            (self.scrape_indeed_rss,    "Indeed PH"),
            (self.scrape_remoteok_api,  "RemoteOK"),
            (self.scrape_jooble,        "Jooble"),
            (self.scrape_philjobnet,    "PhilJobNet"),
            # ── TIER 2: Web Scraping (may vary) ───────────────────────────────
            (self.scrape_linkedin,      "LinkedIn"),
            (self.scrape_jobstreet,     "JobStreet PH"),
            (self.scrape_onlinejobs,    "OnlineJobs.ph"),
            (self.scrape_kalibrr,       "Kalibrr"),
            (self.scrape_bossjob,       "BossJob PH"),
            (self.scrape_trabaho,           "Trabaho.ph"),
            # ── TIER 3: New Sources ────────────────────────────────────────────
            (self.scrape_glassdoor,         "Glassdoor PH"),
            (self.scrape_monster,           "Monster PH"),
            (self.scrape_upwork,            "Upwork"),
            (self.scrape_freelancer,        "Freelancer.com"),
            (self.scrape_jobsdb,            "JobsDB PH"),
            (self.scrape_bestjobs,          "BestJobs PH"),
            (self.scrape_olx,              "OLX PH Jobs"),
            (self.scrape_google_jobs,       "Google Jobs"),
            (self.scrape_telegram_channels, "Telegram PH Jobs"),
        ]

        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(None, fn) for fn, _ in scrapers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_jobs = []
        for (fn, name), result in zip(scrapers, results):
            if isinstance(result, Exception):
                logger.warning(f"❌ {name}: {type(result).__name__}: {result}")
            else:
                count = len(result) if result else 0
                logger.info(f"{'✅' if count > 0 else '⚠️ '} {name}: {count} jobs")
                if result:
                    all_jobs.extend(result)

        # Deduplicate by link
        seen, unique = set(), []
        for job in all_jobs:
            link = job.get("link", "")
            if link and link not in seen:
                seen.add(link)
                unique.append(job)

        # Keep only relevant jobs
        relevant = [j for j in unique if is_relevant(j.get("title", ""), "")]
        logger.info(f"📊 Grand total: {len(all_jobs)} scraped → {len(unique)} unique → {len(relevant)} relevant")
        return relevant

    # ═══════════════════════════════════════════════════════════════════════════
    #  1. INDEED PH — RSS (MOST RELIABLE ✅)
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_indeed_rss(self) -> List[Dict]:
        """
        Indeed RSS feed — very stable, no scraping needed.
        Returns structured XML with title, company, location, salary.
        """
        jobs = []
        searches = [
            "call+center", "BPO+customer+service", "virtual+assistant",
            "work+from+home+Philippines", "POGO+gaming",
            "accounting+Philippines", "IT+support+Philippines",
            "sales+representative+Philippines", "nurse+Philippines",
            "data+entry+Philippines",
        ]
        ns = "https://www.indeed.com/about/"

        for term in searches:
            try:
                url  = f"https://ph.indeed.com/rss?q={term}&l=Philippines&sort=date&limit=25"
                resp = requests.get(url, headers=get_headers(), timeout=TIMEOUT)
                resp.raise_for_status()
                root    = ET.fromstring(resp.content)
                channel = root.find("channel")
                if not channel:
                    continue

                for item in channel.findall("item"):
                    title = item.findtext("title", "")
                    link  = item.findtext("link", "")
                    desc  = item.findtext("description", "")

                    company_el = item.find(f"{{{ns}}}company")
                    company    = company_el.text if company_el is not None else ""

                    city_el  = item.find(f"{{{ns}}}city")
                    state_el = item.find(f"{{{ns}}}state")
                    city     = city_el.text if city_el is not None else ""
                    state    = state_el.text if state_el is not None else ""
                    location = ", ".join(filter(None, [city, state])) or "Philippines"

                    salary_el = item.find(f"{{{ns}}}salary")
                    salary    = salary_el.text if salary_el is not None else None

                    if title and link:
                        jobs.append(make_job(title, company, link, "Indeed PH", location, salary, desc))

                time.sleep(0.3)
            except Exception as e:
                logger.debug(f"Indeed RSS '{term}': {e}")

        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  2. REMOTEOK — JSON API (VERY RELIABLE ✅)
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_remoteok_api(self) -> List[Dict]:
        """
        RemoteOK provides a clean public JSON API — no scraping, no bot detection.
        Great for WFH/Remote jobs that Filipinos can apply to.
        """
        jobs = []
        try:
            resp = requests.get(
                "https://remoteok.com/api",
                headers=get_headers({"Accept": "application/json"}),
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            # First element is a legal notice, skip it
            for job in data[1:] if isinstance(data, list) else []:
                title   = job.get("position", "")
                company = job.get("company", "")
                link    = job.get("url", "")
                tags    = " ".join(job.get("tags", []))
                desc    = job.get("description", "")[:300]

                sal_min = job.get("salary_min")
                sal_max = job.get("salary_max")
                salary  = None
                if sal_min and sal_max:
                    salary = f"${int(sal_min):,}–${int(sal_max):,}/yr"
                elif sal_min:
                    salary = f"${int(sal_min):,}+/yr"

                if title and link and is_relevant(title, tags + " " + desc):
                    jobs.append(make_job(title, company, link, "RemoteOK", "Remote (Worldwide)", salary, desc))

        except Exception as e:
            logger.debug(f"RemoteOK API: {e}")

        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  3. JOOBLE — API with scrape fallback (RELIABLE ✅)
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_jooble(self) -> List[Dict]:
        import os
        API_KEY = os.environ.get("JOOBLE_API_KEY", "")
        jobs    = []
        terms   = [
            "call center", "virtual assistant", "BPO",
            "work from home", "POGO gaming", "customer service",
        ]

        for term in terms:
            try:
                if API_KEY:
                    # Official API — most reliable
                    resp = requests.post(
                        f"https://jooble.org/api/{API_KEY}",
                        json={"keywords": term, "location": "Philippines", "page": 1},
                        headers={"Content-Type": "application/json"},
                        timeout=TIMEOUT,
                    )
                    for j in resp.json().get("jobs", []):
                        title = j.get("title", "")
                        jobs.append(make_job(
                            title,
                            j.get("company", ""),
                            j.get("link", ""),
                            "Jooble",
                            j.get("location", "Philippines"),
                            j.get("salary") or None,
                            j.get("snippet", ""),
                        ))
                else:
                    # Fallback: scrape Jooble PH website
                    url  = f"https://ph.jooble.org/SearchResult?ukw={term.replace(' ', '+')}"
                    resp = requests.get(url, headers=get_headers(), timeout=TIMEOUT)
                    soup = BeautifulSoup(resp.text, "html.parser")

                    for card in soup.find_all("article")[:15]:
                        title_el = card.find(["h2", "h3"])
                        if not title_el:
                            continue
                        title = title_el.get_text(strip=True)
                        a_el  = card.find("a", href=True)
                        link  = a_el["href"] if a_el else ""
                        if link and not link.startswith("http"):
                            link = "https://ph.jooble.org" + link
                        comp_el = card.find(class_=re.compile(r"company|employer", re.I))
                        company = comp_el.get_text(strip=True) if comp_el else ""
                        if title and link:
                            jobs.append(make_job(title, company, link, "Jooble"))

                time.sleep(0.3)
            except Exception as e:
                logger.debug(f"Jooble '{term}': {e}")

        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  4. PHILJOBNET (DOLE) — RSS Feed (RELIABLE ✅)
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_philjobnet(self) -> List[Dict]:
        """Official Philippine government job board from DOLE. Very legit source."""
        jobs = []
        urls = [
            "https://www.philjobnet.gov.ph/rss/jobs",
            "https://www.philjobnet.gov.ph/rss/latest",
        ]

        for url in urls:
            try:
                resp = requests.get(url, headers=get_headers(), timeout=TIMEOUT)
                if resp.status_code != 200:
                    continue
                root    = ET.fromstring(resp.content)
                channel = root.find("channel")
                if not channel:
                    continue

                for item in channel.findall("item")[:40]:
                    title = item.findtext("title", "")
                    link  = item.findtext("link", "")
                    desc  = item.findtext("description", "")

                    if not (title and link):
                        continue
                    if not is_relevant(title, desc):
                        continue

                    # Try to extract company and location from description
                    soup    = BeautifulSoup(desc, "html.parser")
                    text    = soup.get_text()
                    company = ""
                    location = "Philippines"
                    m = re.search(r"(?:Company|Employer):\s*(.+?)(?:\n|<)", text)
                    if m:
                        company = m.group(1).strip()
                    m2 = re.search(r"(?:Location|Address|City):\s*(.+?)(?:\n|<)", text)
                    if m2:
                        location = m2.group(1).strip()

                    jobs.append(make_job(title, company, link, "PhilJobNet", location))

            except Exception as e:
                logger.debug(f"PhilJobNet RSS: {e}")

        # Fallback to web scraping if RSS returns nothing
        if not jobs:
            try:
                for kw in ["call center", "virtual assistant", "BPO"]:
                    url  = f"https://www.philjobnet.gov.ph/index.php?option=com_philjobnet&view=vacancies&task=search&q={kw.replace(' ', '+')}"
                    resp = requests.get(url, headers=get_headers(), timeout=TIMEOUT)
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for row in soup.find_all("tr", class_=re.compile(r"vacancy|job", re.I))[:10]:
                        a = row.find("a", href=True)
                        if not a:
                            continue
                        title = a.get_text(strip=True)
                        link  = a["href"]
                        if not link.startswith("http"):
                            link = "https://www.philjobnet.gov.ph" + link
                        tds   = row.find_all("td")
                        company  = tds[1].get_text(strip=True) if len(tds) > 1 else ""
                        location = tds[2].get_text(strip=True) if len(tds) > 2 else "Philippines"
                        if title:
                            jobs.append(make_job(title, company, link, "PhilJobNet", location))
            except Exception as e:
                logger.debug(f"PhilJobNet scrape fallback: {e}")

        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  5. LINKEDIN — Public search (updated selectors + anti-block headers)
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_linkedin(self) -> List[Dict]:
        """
        LinkedIn public job listings — works without login.
        Updated selectors and headers to reduce blocking.
        Multiple CSS strategies since LinkedIn changes HTML frequently.
        """
        jobs = []
        searches = [
            ("call center agent Philippines", "Philippines"),
            ("virtual assistant Philippines", "Philippines"),
            ("BPO customer service Philippines", "Philippines"),
            ("work from home Philippines", "Philippines"),
            ("POGO online gaming Philippines", "Philippines"),
        ]

        for keywords, location in searches:
            try:
                kw_enc  = requests.utils.quote(keywords)
                loc_enc = requests.utils.quote(location)
                url     = (
                    f"https://www.linkedin.com/jobs/search?"
                    f"keywords={kw_enc}&location={loc_enc}"
                    f"&f_TPR=r86400&sortBy=DD&position=1&pageNum=0"
                )
                headers = get_headers({
                    "Referer":            "https://www.linkedin.com/jobs/",
                    "sec-ch-ua":          '"Not_A Brand";v="8", "Chromium";v="121"',
                    "sec-ch-ua-mobile":   "?0",
                    "sec-ch-ua-platform": '"Windows"',
                    "Sec-Fetch-Dest":     "document",
                    "Sec-Fetch-Mode":     "navigate",
                    "Sec-Fetch-Site":     "same-origin",
                })
                resp = requests.get(url, headers=headers, timeout=TIMEOUT)

                # LinkedIn returns 429/999 when blocking scrapers
                if resp.status_code in (429, 403, 999):
                    logger.debug(f"LinkedIn blocked ({resp.status_code}): {keywords}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")

                # Strategy 1: JSON-LD (most reliable when available)
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data  = json.loads(script.string or "")
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get("@type") == "JobPosting":
                                title   = item.get("title", "")
                                company = item.get("hiringOrganization", {}).get("name", "")
                                link    = item.get("url", "")
                                loc_raw = item.get("jobLocation", {})
                                loc_str = "Philippines"
                                if isinstance(loc_raw, dict):
                                    loc_str = loc_raw.get("address", {}).get("addressLocality", "Philippines")
                                if title and link:
                                    jobs.append(make_job(title, company, link, "LinkedIn", loc_str))
                    except Exception:
                        pass

                # Strategy 2: CSS selectors (multiple attempts for LI versions)
                cards = (
                    soup.find_all("div", class_=re.compile(r"base-card|job-search-card|base-search-card", re.I))
                    or soup.find_all("li", class_=re.compile(r"result-card|jobs-search-results__list-item", re.I))
                    or soup.find_all("div", attrs={"data-entity-urn": re.compile(r"jobPosting", re.I)})
                )

                for card in cards[:10]:
                    title_el = (
                        card.find("h3", class_=re.compile(r"title|base-search-card__title", re.I))
                        or card.find("h3")
                        or card.find("h2")
                    )
                    if not title_el:
                        continue

                    title = title_el.get_text(strip=True)
                    a_el  = card.find("a", href=True)
                    link  = ""
                    if a_el:
                        link = a_el["href"].split("?")[0]
                        if not link.startswith("http"):
                            link = "https://www.linkedin.com" + link

                    comp_el = (
                        card.find(class_=re.compile(r"base-search-card__subtitle|company-name|subtitle", re.I))
                        or card.find("h4")
                    )
                    company = comp_el.get_text(strip=True) if comp_el else ""

                    loc_el  = card.find(class_=re.compile(r"job-search-card__location|base-search-card__metadata|location", re.I))
                    job_loc = loc_el.get_text(strip=True) if loc_el else "Philippines"

                    if title and link and "linkedin.com" in link:
                        jobs.append(make_job(title, company, link, "LinkedIn", job_loc))

                time.sleep(2.0)  # longer delay to avoid rate-limiting
            except Exception as e:
                logger.debug(f"LinkedIn '{keywords}': {e}")

        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  6. JOBSTREET PH — JSON-LD extraction (more reliable than CSS scraping)
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_jobstreet(self) -> List[Dict]:
        """
        Uses JSON-LD structured data embedded in the page — more stable
        than CSS class scraping because class names change frequently.
        """
        jobs = []
        pages = [
            "https://www.jobstreet.com.ph/call-center-jobs",
            "https://www.jobstreet.com.ph/bpo-jobs",
            "https://www.jobstreet.com.ph/virtual-assistant-jobs",
            "https://www.jobstreet.com.ph/customer-service-jobs",
            "https://www.jobstreet.com.ph/work-from-home-jobs",
            "https://www.jobstreet.com.ph/accounting-jobs",
            "https://www.jobstreet.com.ph/information-technology-jobs",
            "https://www.jobstreet.com.ph/healthcare-nursing-jobs",
        ]

        for url in pages:
            try:
                resp = requests.get(url, headers=get_headers(), timeout=TIMEOUT)
                if resp.status_code == 403:
                    logger.debug(f"JobStreet 403 blocked: {url}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")

                # Method 1: JSON-LD structured data (most reliable)
                found_jsonld = False
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data  = json.loads(script.string or "")
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get("@type") != "JobPosting":
                                continue
                            title   = item.get("title", "")
                            company = item.get("hiringOrganization", {}).get("name", "")
                            link    = item.get("url") or item.get("sameAs", "")
                            loc_raw = item.get("jobLocation", {})
                            location = "Philippines"
                            if isinstance(loc_raw, dict):
                                location = loc_raw.get("address", {}).get("addressLocality", "Philippines")

                            sal_data = item.get("baseSalary", {})
                            salary = None
                            if isinstance(sal_data, dict):
                                val = sal_data.get("value", {})
                                if isinstance(val, dict):
                                    mn = val.get("minValue")
                                    mx = val.get("maxValue")
                                    curr = sal_data.get("currency", "PHP")
                                    if mn and mx:
                                        salary = f"{curr} {int(mn):,}–{int(mx):,}"

                            if title and link:
                                jobs.append(make_job(title, company, link, "JobStreet PH", location, salary))
                                found_jsonld = True
                    except Exception:
                        pass

                # Method 2: next.js __NEXT_DATA__ JSON (if JSON-LD not found)
                if not found_jsonld:
                    next_data = soup.find("script", id="__NEXT_DATA__")
                    if next_data:
                        try:
                            data = json.loads(next_data.string or "{}")
                            # Walk the nested structure to find job listings
                            job_list = (
                                data.get("props", {})
                                    .get("pageProps", {})
                                    .get("jobSearchResult", {})
                                    .get("jobs", [])
                            )
                            for j in job_list[:15]:
                                title   = j.get("title", "") or j.get("roleTitles", [""])[0]
                                company = j.get("companyName", "") or j.get("advertiser", {}).get("description", "")
                                job_id  = j.get("id", "")
                                link    = f"https://www.jobstreet.com.ph/job/{job_id}" if job_id else ""
                                location = j.get("locationWhereYouCanWork", [{}])[0].get("label", "Philippines") if j.get("locationWhereYouCanWork") else "Philippines"
                                if title and link:
                                    jobs.append(make_job(title, company, link, "JobStreet PH", location))
                        except Exception:
                            pass

                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"JobStreet '{url}': {e}")

        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  7. ONLINEJOBS.PH — Best for VA & Remote PH jobs
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_onlinejobs(self) -> List[Dict]:
        jobs = []
        searches = [
            "virtual-assistant", "data-entry", "customer-service",
            "social-media", "bookkeeper", "content-writer",
            "graphic-designer", "web-developer",
        ]

        for kw in searches:
            try:
                url  = f"https://www.onlinejobs.ph/jobseekers/joblist/1?keyword={kw}&jobtype=1&category=0"
                resp = requests.get(url, headers=get_headers(), timeout=TIMEOUT)
                soup = BeautifulSoup(resp.text, "html.parser")

                # Try JSON-LD first
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data  = json.loads(script.string or "")
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get("@type") == "JobPosting":
                                title   = item.get("title", "")
                                company = item.get("hiringOrganization", {}).get("name", "Remote Employer")
                                link    = item.get("url", "")
                                if title and link:
                                    jobs.append(make_job(title, company, link, "OnlineJobs.ph", "Philippines (Remote)"))
                    except Exception:
                        pass

                # Fallback: DOM scraping
                for card in soup.find_all("div", class_=re.compile(r"job.?post|jobpost|job.?row", re.I))[:12]:
                    a = card.find("a", href=True)
                    if not a:
                        continue
                    title = a.get_text(strip=True)
                    link  = a["href"]
                    if not link.startswith("http"):
                        link = "https://www.onlinejobs.ph" + link
                    comp_el = card.find(class_=re.compile(r"company|employer|client", re.I))
                    company = comp_el.get_text(strip=True) if comp_el else "Remote Employer"
                    rate_el = card.find(class_=re.compile(r"rate|salary|pay", re.I))
                    salary  = rate_el.get_text(strip=True) if rate_el else None
                    if title and link:
                        jobs.append(make_job(title, company, link, "OnlineJobs.ph", "Philippines (Remote)", salary))

                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"OnlineJobs '{kw}': {e}")

        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  8. KALIBRR — JSON-LD + Next.js data
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_kalibrr(self) -> List[Dict]:
        jobs = []
        searches = [
            "call+center", "virtual+assistant", "BPO",
            "customer+service", "work+from+home",
        ]

        for kw in searches:
            try:
                url  = f"https://www.kalibrr.com/job-board/te/philippines?q={kw}&sort=recent"
                resp = requests.get(url, headers=get_headers(), timeout=TIMEOUT)
                if resp.status_code == 403:
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")

                # JSON-LD
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data  = json.loads(script.string or "")
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get("@type") == "JobPosting":
                                title   = item.get("title", "")
                                company = item.get("hiringOrganization", {}).get("name", "")
                                link    = item.get("url", "")
                                loc_raw = item.get("jobLocation", {})
                                location = "Philippines"
                                if isinstance(loc_raw, dict):
                                    location = loc_raw.get("address", {}).get("addressLocality", "Philippines")
                                if title and link:
                                    jobs.append(make_job(title, company, link, "Kalibrr", location))
                    except Exception:
                        pass

                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"Kalibrr '{kw}': {e}")

        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  9. BOSSJOB PH
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_bossjob(self) -> List[Dict]:
        jobs = []
        searches = ["call+center", "virtual+assistant", "customer+service", "bpo"]

        for kw in searches:
            try:
                url  = f"https://ph.bossjob.com/jobs?search={kw}&sort=latest"
                resp = requests.get(url, headers=get_headers(), timeout=TIMEOUT)
                if resp.status_code == 403:
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")

                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data  = json.loads(script.string or "")
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get("@type") == "JobPosting":
                                title   = item.get("title", "")
                                company = item.get("hiringOrganization", {}).get("name", "")
                                link    = item.get("url", "")
                                sal_data = item.get("baseSalary", {})
                                salary = None
                                if isinstance(sal_data, dict):
                                    val = sal_data.get("value", {})
                                    if isinstance(val, dict):
                                        mn = val.get("minValue")
                                        mx = val.get("maxValue")
                                        if mn:
                                            salary = f"PHP {int(mn):,}–{int(mx):,}" if mx else f"PHP {int(mn):,}+"
                                if title and link:
                                    jobs.append(make_job(title, company, link, "BossJob PH", "Philippines", salary))
                    except Exception:
                        pass

                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"BossJob '{kw}': {e}")

        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  10. TRABAHO.PH
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_trabaho(self) -> List[Dict]:
        jobs = []
        searches = ["call-center", "virtual-assistant", "bpo", "work-from-home"]

        for kw in searches:
            try:
                url  = f"https://trabaho.ph/jobs?q={kw}&sort=newest"
                resp = requests.get(url, headers=get_headers(), timeout=TIMEOUT)
                if resp.status_code == 403:
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")

                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data  = json.loads(script.string or "")
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get("@type") == "JobPosting":
                                title   = item.get("title", "")
                                company = item.get("hiringOrganization", {}).get("name", "")
                                link    = item.get("url", "")
                                if title and link:
                                    jobs.append(make_job(title, company, link, "Trabaho.ph"))
                    except Exception:
                        pass

                # DOM fallback
                for card in soup.find_all("div", class_=re.compile(r"job.?item|job.?listing|vacancy", re.I))[:10]:
                    title_el = card.find(["h2", "h3", "a"])
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    a_el  = card.find("a", href=True)
                    link  = a_el["href"] if a_el else ""
                    if link and not link.startswith("http"):
                        link = "https://trabaho.ph" + link
                    comp_el  = card.find(class_=re.compile(r"company|employer", re.I))
                    company  = comp_el.get_text(strip=True) if comp_el else ""
                    loc_el   = card.find(class_=re.compile(r"location|city", re.I))
                    location = loc_el.get_text(strip=True) if loc_el else "Philippines"
                    if title and link:
                        jobs.append(make_job(title, company, link, "Trabaho.ph", location))

                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"Trabaho '{kw}': {e}")

        return jobs


    # ═══════════════════════════════════════════════════════════════════════════
    #  ★ NEW SOURCES ADDED BELOW (still inside JobScraper class)
    # ═══════════════════════════════════════════════════════════════════════════

    # ─────────────────────────────────────────────────────────────────────────
    #  11. GLASSDOOR PH — Job listings + salary info
    # ─────────────────────────────────────────────────────────────────────────
    def scrape_glassdoor(self) -> List[Dict]:
        jobs = []
        searches = [
            "call-center", "virtual-assistant", "BPO",
            "customer-service", "work-from-home",
        ]
        for kw in searches:
            try:
                url  = f"https://www.glassdoor.com/Job/philippines-{kw}-jobs-SRCH_IL.0,11_IN194_KO12,{12+len(kw)}.htm?sortBy=date_desc"
                resp = requests.get(url, headers=get_headers({"Referer": "https://www.glassdoor.com/"}), timeout=TIMEOUT)
                if resp.status_code in (403, 429):
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")

                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data  = json.loads(script.string or "")
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get("@type") == "JobPosting":
                                title   = item.get("title", "")
                                company = item.get("hiringOrganization", {}).get("name", "")
                                link    = item.get("url", "")
                                sal_data = item.get("baseSalary", {})
                                salary = None
                                if isinstance(sal_data, dict):
                                    val = sal_data.get("value", {})
                                    if isinstance(val, dict):
                                        mn   = val.get("minValue")
                                        mx   = val.get("maxValue")
                                        curr = sal_data.get("currency", "PHP")
                                        if mn and mx:
                                            salary = f"{curr} {int(mn):,}–{int(mx):,}"
                                if title and link:
                                    jobs.append(make_job(title, company, link, "Glassdoor PH", "Philippines", salary))
                    except Exception:
                        pass
                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"Glassdoor '{kw}': {e}")
        return jobs

    # ─────────────────────────────────────────────────────────────────────────
    #  12. MONSTER PH — Job board
    # ─────────────────────────────────────────────────────────────────────────
    def scrape_monster(self) -> List[Dict]:
        jobs = []
        searches = [
            "call-center", "virtual-assistant", "bpo",
            "customer-service", "work-from-home",
        ]
        for kw in searches:
            try:
                url  = f"https://www.monster.com.ph/jobs/search/?q={kw}&where=Philippines&sort=dt.desc"
                resp = requests.get(url, headers=get_headers(), timeout=TIMEOUT)
                if resp.status_code in (403, 429):
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")

                # JSON-LD first
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data  = json.loads(script.string or "")
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get("@type") == "JobPosting":
                                title   = item.get("title", "")
                                company = item.get("hiringOrganization", {}).get("name", "")
                                link    = item.get("url", "")
                                if title and link:
                                    jobs.append(make_job(title, company, link, "Monster PH"))
                    except Exception:
                        pass

                # DOM fallback
                for card in soup.find_all("div", class_=re.compile(r"job.?card|job-summary|result", re.I))[:12]:
                    title_el = card.find(["h2", "h3", "a"])
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    a_el  = card.find("a", href=True)
                    link  = a_el["href"] if a_el else ""
                    if link and not link.startswith("http"):
                        link = "https://www.monster.com.ph" + link
                    comp_el = card.find(class_=re.compile(r"company|employer|name", re.I))
                    company = comp_el.get_text(strip=True) if comp_el else ""
                    if title and link and is_relevant(title):
                        jobs.append(make_job(title, company, link, "Monster PH"))
                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"Monster '{kw}': {e}")
        return jobs

    # ─────────────────────────────────────────────────────────────────────────
    #  13. UPWORK — Remote Freelance Jobs (RSS Feed ✅)
    # ─────────────────────────────────────────────────────────────────────────
    def scrape_upwork(self) -> List[Dict]:
        """
        Upwork has public RSS feeds for job searches — very reliable.
        Great for VA, data entry, customer service freelance jobs.
        """
        jobs = []
        rss_searches = [
            "virtual+assistant",
            "customer+service+Philippines",
            "data+entry",
            "social+media+manager",
            "bookkeeper",
            "content+writer",
            "graphic+designer",
            "web+developer+Philippines",
        ]
        for term in rss_searches:
            try:
                url  = f"https://www.upwork.com/ab/feed/jobs/rss?q={term}&sort=recency&paging=0%3B10"
                resp = requests.get(url, headers=get_headers({"Accept": "application/rss+xml, application/xml"}), timeout=TIMEOUT)
                if resp.status_code != 200:
                    continue
                root    = ET.fromstring(resp.content)
                channel = root.find("channel")
                if not channel:
                    continue
                for item in channel.findall("item"):
                    title = item.findtext("title", "")
                    link  = item.findtext("link", "")
                    desc  = item.findtext("description", "")
                    if title and link and is_relevant(title, desc):
                        # Extract budget from description if available
                        salary = None
                        m = re.search(r"Budget:\s*\$?([\d,]+(?:\s*[-–]\s*\$?[\d,]+)?)", desc)
                        if m:
                            salary = f"${m.group(1)}"
                        jobs.append(make_job(title, "Upwork Client", link, "Upwork", "Remote (Worldwide)", salary, desc))
                time.sleep(0.3)
            except Exception as e:
                logger.debug(f"Upwork RSS '{term}': {e}")
        return jobs

    # ─────────────────────────────────────────────────────────────────────────
    #  14. FREELANCER.COM — Freelance / Remote (RSS Feed ✅)
    # ─────────────────────────────────────────────────────────────────────────
    def scrape_freelancer(self) -> List[Dict]:
        """
        Freelancer.com has public RSS feeds — stable and no login needed.
        """
        jobs = []
        searches = [
            "virtual-assistant",
            "customer-service",
            "data-entry",
            "social-media",
            "content-writing",
        ]
        for kw in searches:
            try:
                url  = f"https://www.freelancer.com/rss/search/{kw}.xml"
                resp = requests.get(url, headers=get_headers(), timeout=TIMEOUT)
                if resp.status_code != 200:
                    continue
                root    = ET.fromstring(resp.content)
                channel = root.find("channel")
                if not channel:
                    continue
                for item in channel.findall("item")[:15]:
                    title = item.findtext("title", "")
                    link  = item.findtext("link", "")
                    desc  = item.findtext("description", "")
                    if title and link and is_relevant(title, desc):
                        # Extract budget from title or desc
                        salary = None
                        m = re.search(r"\$([\d,]+(?:\s*[-–]\s*[\d,]+)?)", title + " " + desc)
                        if m:
                            salary = f"${m.group(1)}"
                        jobs.append(make_job(title, "Freelancer Client", link, "Freelancer.com", "Remote (Worldwide)", salary, desc))
                time.sleep(0.3)
            except Exception as e:
                logger.debug(f"Freelancer.com RSS '{kw}': {e}")
        return jobs

    # ─────────────────────────────────────────────────────────────────────────
    #  15. JOBSDB PH — Popular PH job board
    # ─────────────────────────────────────────────────────────────────────────
    def scrape_jobsdb(self) -> List[Dict]:
        jobs = []
        searches = [
            "call-center", "virtual-assistant", "bpo",
            "customer-service", "work-from-home",
        ]
        for kw in searches:
            try:
                url  = f"https://ph.jobsdb.com/ph/search-jobs/{kw}/1?sortMode=1"
                resp = requests.get(url, headers=get_headers(), timeout=TIMEOUT)
                if resp.status_code in (403, 429):
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")

                # JSON-LD
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data  = json.loads(script.string or "")
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get("@type") == "JobPosting":
                                title   = item.get("title", "")
                                company = item.get("hiringOrganization", {}).get("name", "")
                                link    = item.get("url", "")
                                sal_data = item.get("baseSalary", {})
                                salary = None
                                if isinstance(sal_data, dict):
                                    val = sal_data.get("value", {})
                                    if isinstance(val, dict):
                                        mn = val.get("minValue")
                                        mx = val.get("maxValue")
                                        if mn:
                                            salary = f"PHP {int(mn):,}–{int(mx):,}" if mx else f"PHP {int(mn):,}+"
                                if title and link:
                                    jobs.append(make_job(title, company, link, "JobsDB PH", "Philippines", salary))
                    except Exception:
                        pass

                # Next.js data fallback
                next_data = soup.find("script", id="__NEXT_DATA__")
                if next_data:
                    try:
                        data = json.loads(next_data.string or "{}")
                        job_list = (
                            data.get("props", {})
                                .get("pageProps", {})
                                .get("jobs", [])
                        )
                        for j in job_list[:15]:
                            title   = j.get("title", "")
                            company = j.get("advertiser", {}).get("description", "")
                            job_id  = j.get("id", "")
                            link    = f"https://ph.jobsdb.com/job/{job_id}" if job_id else ""
                            if title and link:
                                jobs.append(make_job(title, company, link, "JobsDB PH"))
                    except Exception:
                        pass

                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"JobsDB '{kw}': {e}")
        return jobs

    # ─────────────────────────────────────────────────────────────────────────
    #  16. BESTJOBS PH — Local PH job board
    # ─────────────────────────────────────────────────────────────────────────
    def scrape_bestjobs(self) -> List[Dict]:
        jobs = []
        searches = ["call-center", "bpo", "virtual-assistant", "customer-service"]
        for kw in searches:
            try:
                url  = f"https://www.bestjobs.ph/jobs?search={kw}&sort=newest"
                resp = requests.get(url, headers=get_headers(), timeout=TIMEOUT)
                if resp.status_code in (403, 429):
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")

                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data  = json.loads(script.string or "")
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get("@type") == "JobPosting":
                                title   = item.get("title", "")
                                company = item.get("hiringOrganization", {}).get("name", "")
                                link    = item.get("url", "")
                                if title and link:
                                    jobs.append(make_job(title, company, link, "BestJobs PH"))
                    except Exception:
                        pass

                for card in soup.find_all("div", class_=re.compile(r"job.?card|vacancy|listing", re.I))[:10]:
                    title_el = card.find(["h2", "h3", "a"])
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    a_el  = card.find("a", href=True)
                    link  = a_el["href"] if a_el else ""
                    if link and not link.startswith("http"):
                        link = "https://www.bestjobs.ph" + link
                    comp_el = card.find(class_=re.compile(r"company|employer", re.I))
                    company = comp_el.get_text(strip=True) if comp_el else ""
                    if title and link and is_relevant(title):
                        jobs.append(make_job(title, company, link, "BestJobs PH"))
                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"BestJobs '{kw}': {e}")
        return jobs

    # ─────────────────────────────────────────────────────────────────────────
    #  17. OLX PH — Jobs section
    # ─────────────────────────────────────────────────────────────────────────
    def scrape_olx(self) -> List[Dict]:
        jobs = []
        searches = ["call-center", "bpo", "virtual-assistant", "customer-service", "work-from-home"]
        for kw in searches:
            try:
                url  = f"https://www.olx.ph/jobs/?search%5Bfilter_str_category%5D=jobs&search%5Bq%5D={kw.replace('-', '+')}&s=newest_first"
                resp = requests.get(url, headers=get_headers(), timeout=TIMEOUT)
                if resp.status_code in (403, 429):
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")

                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data  = json.loads(script.string or "")
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get("@type") in ("JobPosting", "Product"):
                                title   = item.get("title", "") or item.get("name", "")
                                link    = item.get("url", "")
                                company = item.get("hiringOrganization", {}).get("name", "") if item.get("@type") == "JobPosting" else "OLX Poster"
                                if title and link and is_relevant(title):
                                    jobs.append(make_job(title, company, link, "OLX PH Jobs"))
                    except Exception:
                        pass

                for card in soup.find_all("li", class_=re.compile(r"offer|listing|item", re.I))[:10]:
                    title_el = card.find(["h3", "h4", "strong"])
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    a_el  = card.find("a", href=True)
                    link  = a_el["href"] if a_el else ""
                    if link and not link.startswith("http"):
                        link = "https://www.olx.ph" + link
                    sal_el = card.find(class_=re.compile(r"price|salary", re.I))
                    salary = sal_el.get_text(strip=True) if sal_el else None
                    if title and link and is_relevant(title):
                        jobs.append(make_job(title, "OLX Poster", link, "OLX PH Jobs", "Philippines", salary))
                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"OLX '{kw}': {e}")
        return jobs

    # ─────────────────────────────────────────────────────────────────────────
    #  18. GOOGLE JOBS via SerpAPI (optional — needs free API key)
    # ─────────────────────────────────────────────────────────────────────────
    def scrape_google_jobs(self) -> List[Dict]:
        """
        Uses SerpAPI free tier (100 searches/month free).
        Set SERPAPI_KEY in Railway environment variables to enable.
        Get free key at: https://serpapi.com/
        """
        import os
        API_KEY = os.environ.get("SERPAPI_KEY", "")
        if not API_KEY:
            return []

        jobs = []
        searches = [
            "call center jobs Philippines",
            "virtual assistant jobs Philippines",
            "BPO jobs Philippines",
            "work from home jobs Philippines",
            "POGO jobs Philippines",
        ]
        for q in searches:
            try:
                resp = requests.get(
                    "https://serpapi.com/search",
                    params={
                        "engine":   "google_jobs",
                        "q":        q,
                        "location": "Philippines",
                        "api_key":  API_KEY,
                        "chips":    "date_posted:today",
                    },
                    timeout=TIMEOUT,
                )
                data = resp.json()
                for j in data.get("jobs_results", []):
                    title    = j.get("title", "")
                    company  = j.get("company_name", "")
                    location = j.get("location", "Philippines")
                    link     = j.get("related_links", [{}])[0].get("link", "") or j.get("share_link", "")
                    salary   = None
                    sal_data = j.get("detected_extensions", {})
                    if sal_data.get("salary"):
                        salary = sal_data["salary"]
                    if title and link:
                        jobs.append(make_job(title, company, link, "Google Jobs", location, salary))
                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"Google Jobs '{q}': {e}")
        return jobs

    # ─────────────────────────────────────────────────────────────────────────
    #  19. TELEGRAM PUBLIC JOB CHANNELS (via t.me preview — no bot needed)
    # ─────────────────────────────────────────────────────────────────────────
    def scrape_telegram_channels(self) -> List[Dict]:
        """
        Scrapes public Telegram job channels via t.me web preview.
        No login needed — works on public channels only.
        These are known active PH job posting channels.
        """
        jobs = []

        # List of known public PH job Telegram channels
        channels = [
            "PHJobHunters",
            "PHJobVacancy",
            "jobshiringph",
            "PHJobsOnline",
            "bpojobsph",
            "virtualassistantph",
            "pogoworkph",
        ]

        for channel in channels:
            try:
                url  = f"https://t.me/s/{channel}"
                resp = requests.get(url, headers=get_headers({"Accept": "text/html"}), timeout=TIMEOUT)
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")

                messages = soup.find_all("div", class_="tgme_widget_message_text")

                for msg in messages[:20]:
                    text = msg.get_text(separator=" ", strip=True)
                    if not text or len(text) < 30:
                        continue

                    # Check if it's a job post
                    if not is_relevant(text[:200]):
                        continue

                    # Extract title — usually first line or after "HIRING:"
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    title = ""
                    for line in lines[:3]:
                        if any(kw.lower() in line.lower() for kw in ["hiring", "looking for", "vacancy", "job", "position", "needed", "wanted"]):
                            title = line[:100]
                            break
                    if not title and lines:
                        title = lines[0][:100]

                    if not title:
                        continue

                    # Get the message link
                    link_el = msg.find_parent("div", class_="tgme_widget_message")
                    msg_link = ""
                    if link_el:
                        data_post = link_el.get("data-post", "")
                        if data_post:
                            msg_link = f"https://t.me/{data_post}"

                    if not msg_link:
                        msg_link = f"https://t.me/s/{channel}"

                    # Try to extract company/salary from the text
                    company = ""
                    m = re.search(r"(?:company|employer|client):\s*(.+?)(?:\n|$)", text, re.I)
                    if m:
                        company = m.group(1).strip()[:80]

                    salary = None
                    m2 = re.search(r"(?:salary|pay|rate|compensation):\s*(.+?)(?:\n|$)", text, re.I)
                    if m2:
                        salary = m2.group(1).strip()[:60]

                    jobs.append(make_job(
                        title,
                        company or f"@{channel}",
                        msg_link,
                        "Telegram PH Jobs",
                        "Philippines",
                        salary,
                        text[:300],
                    ))

                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"Telegram channel '@{channel}': {e}")

        return jobs
