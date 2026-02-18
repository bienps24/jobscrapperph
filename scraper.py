"""
Job Scrapper PH — Rebuilt for Reliability (FIXED VERSION)
==========================================
Priority: RSS Feeds & APIs first (most stable), Web Scraping as fallback.

FIXES APPLIED:
  - Indeed RSS namespace fixed (http:// not https://)
  - LinkedIn improved headers + authwall detection + session cookies
  - PhilJobNet RSS URLs corrected
  - Upwork RSS URL updated to current format with fallback
  - Freelancer.com RSS URL fixed with fallback to web scrape
  - Session-based requests for bot-protected sites (JobStreet, Kalibrr, etc.)
  - Retry logic added globally via HTTPAdapter
  - Trabaho.ph URL format fixed (tries multiple formats)
  - Filter default changed from 'Lahat' to 'All' (see database.py fix)
"""

import asyncio
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from typing import List, Dict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ─── Rotate User Agents ────────────────────────────────────────────────────────
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
        "Accept-Language": "en-US,en;q=0.9,fil;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
    if extra:
        h.update(extra)
    return h


def create_session() -> requests.Session:
    """Create a requests Session with retry logic and browser-like settings."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.cookies.update({
        "euconsent-v2": "accepted",
        "cookieconsent_status": "dismiss",
    })
    return session


TIMEOUT = 20  # seconds per request


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
        scrapers = [
            # TIER 1: RSS Feeds & APIs (most reliable)
            (self.scrape_indeed_rss,        "Indeed PH"),
            (self.scrape_remoteok_api,      "RemoteOK"),
            (self.scrape_jooble,            "Jooble"),
            (self.scrape_philjobnet,        "PhilJobNet"),
            # TIER 2: Web Scraping
            (self.scrape_linkedin,          "LinkedIn"),
            (self.scrape_jobstreet,         "JobStreet PH"),
            (self.scrape_onlinejobs,        "OnlineJobs.ph"),
            (self.scrape_kalibrr,           "Kalibrr"),
            (self.scrape_bossjob,           "BossJob PH"),
            (self.scrape_trabaho,           "Trabaho.ph"),
            # TIER 3: Additional Sources
            (self.scrape_glassdoor,         "Glassdoor PH"),
            (self.scrape_monster,           "Monster PH"),
            (self.scrape_upwork,            "Upwork"),
            (self.scrape_freelancer,        "Freelancer.com"),
            (self.scrape_jobsdb,            "JobsDB PH"),
            (self.scrape_olx,               "OLX PH Jobs"),
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

        relevant = [j for j in unique if is_relevant(j.get("title", ""), "")]
        logger.info(f"📊 Grand total: {len(all_jobs)} scraped → {len(unique)} unique → {len(relevant)} relevant")
        return relevant

    # ═══════════════════════════════════════════════════════════════════════════
    #  1. INDEED PH — RSS (FIXED: namespace was https://, should be http://)
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_indeed_rss(self) -> List[Dict]:
        jobs = []
        searches = [
            "call+center", "BPO+customer+service", "virtual+assistant",
            "work+from+home+Philippines", "POGO+gaming",
            "accounting+Philippines", "IT+support+Philippines",
            "sales+representative+Philippines", "nurse+Philippines",
            "data+entry+Philippines",
        ]
        # BUG FIX: Indeed uses http:// (not https://) in their RSS namespace
        NS_OPTIONS = [
            "http://www.indeed.com/about/",   # correct
            "https://www.indeed.com/about/",  # fallback
        ]
        session = create_session()

        for term in searches:
            try:
                url  = f"https://ph.indeed.com/rss?q={term}&l=Philippines&sort=date&limit=25"
                resp = session.get(url, headers=get_headers(), timeout=TIMEOUT)
                resp.raise_for_status()
                root    = ET.fromstring(resp.content)
                channel = root.find("channel")
                if not channel:
                    continue

                for item in channel.findall("item"):
                    title = item.findtext("title", "")
                    link  = item.findtext("link", "")
                    desc  = item.findtext("description", "")

                    company  = ""
                    location = "Philippines"
                    salary   = None

                    # Try both namespaces
                    for ns in NS_OPTIONS:
                        company_el = item.find(f"{{{ns}}}company")
                        if company_el is not None and company_el.text:
                            company = company_el.text
                        city_el  = item.find(f"{{{ns}}}city")
                        state_el = item.find(f"{{{ns}}}state")
                        city     = city_el.text if city_el is not None else ""
                        state    = state_el.text if state_el is not None else ""
                        if city or state:
                            location = ", ".join(filter(None, [city, state]))
                        salary_el = item.find(f"{{{ns}}}salary")
                        if salary_el is not None and salary_el.text:
                            salary = salary_el.text
                        if company:
                            break

                    if title and link:
                        jobs.append(make_job(title, company, link, "Indeed PH", location, salary, desc))

                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"Indeed RSS '{term}': {e}")

        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  2. REMOTEOK — JSON API (Very Reliable)
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_remoteok_api(self) -> List[Dict]:
        jobs = []
        try:
            resp = requests.get(
                "https://remoteok.com/api",
                headers=get_headers({"Accept": "application/json"}),
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

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
    #  3. JOOBLE — API with scrape fallback
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_jooble(self) -> List[Dict]:
        API_KEY = os.environ.get("JOOBLE_API_KEY", "")
        jobs    = []
        terms   = ["call center", "virtual assistant", "BPO", "work from home", "customer service"]
        session = create_session()

        for term in terms:
            try:
                if API_KEY:
                    resp = requests.post(
                        f"https://jooble.org/api/{API_KEY}",
                        json={"keywords": term, "location": "Philippines", "page": 1},
                        headers={"Content-Type": "application/json"},
                        timeout=TIMEOUT,
                    )
                    for j in resp.json().get("jobs", []):
                        jobs.append(make_job(
                            j.get("title", ""), j.get("company", ""), j.get("link", ""),
                            "Jooble", j.get("location", "Philippines"),
                            j.get("salary") or None, j.get("snippet", ""),
                        ))
                else:
                    url  = f"https://ph.jooble.org/SearchResult?ukw={term.replace(' ', '+')}"
                    resp = session.get(url, headers=get_headers(), timeout=TIMEOUT)
                    if resp.status_code == 403:
                        continue
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
                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"Jooble '{term}': {e}")

        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  4. PHILJOBNET (DOLE) — FIXED RSS URLs
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_philjobnet(self) -> List[Dict]:
        """BUG FIXED: Old RSS paths /rss/jobs and /rss/latest didn't exist."""
        jobs    = []
        session = create_session()

        # FIXED: Correct PhilJobNet RSS URL formats
        rss_urls = [
            "https://www.philjobnet.gov.ph/index.php?option=com_philjobnet&view=vacancies&format=feed&type=rss",
            "https://www.philjobnet.gov.ph/rss.xml",
            "https://www.philjobnet.gov.ph/feed/",
        ]

        for url in rss_urls:
            try:
                resp = session.get(url, headers=get_headers(), timeout=TIMEOUT)
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
                    if not (title and link) or not is_relevant(title, desc):
                        continue
                    soup     = BeautifulSoup(desc, "html.parser")
                    text     = soup.get_text()
                    company  = ""
                    location = "Philippines"
                    m = re.search(r"(?:Company|Employer):\s*(.+?)(?:\n|<)", text)
                    if m:
                        company = m.group(1).strip()
                    m2 = re.search(r"(?:Location|Address|City):\s*(.+?)(?:\n|<)", text)
                    if m2:
                        location = m2.group(1).strip()
                    jobs.append(make_job(title, company, link, "PhilJobNet", location))

                if jobs:
                    break
            except Exception as e:
                logger.debug(f"PhilJobNet RSS '{url}': {e}")

        # Fallback: web scrape
        if not jobs:
            try:
                for kw in ["call center", "virtual assistant", "BPO", "nursing"]:
                    url  = f"https://www.philjobnet.gov.ph/index.php?option=com_philjobnet&view=vacancies&task=search&q={kw.replace(' ', '+')}"
                    resp = session.get(url, headers=get_headers(), timeout=TIMEOUT)
                    if resp.status_code != 200:
                        continue
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for row in soup.find_all(["div", "tr"], class_=re.compile(r"vacancy|job|result", re.I))[:10]:
                        a = row.find("a", href=True)
                        if not a:
                            continue
                        title = a.get_text(strip=True)
                        link  = a["href"]
                        if not link.startswith("http"):
                            link = "https://www.philjobnet.gov.ph" + link
                        tds      = row.find_all("td")
                        company  = tds[1].get_text(strip=True) if len(tds) > 1 else ""
                        location = tds[2].get_text(strip=True) if len(tds) > 2 else "Philippines"
                        if title and is_relevant(title):
                            jobs.append(make_job(title, company, link, "PhilJobNet", location))
            except Exception as e:
                logger.debug(f"PhilJobNet scrape fallback: {e}")

        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  5. LINKEDIN — IMPROVED (Session + better headers + authwall detection)
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_linkedin(self) -> List[Dict]:
        """
        BUG FIXED:
        - Added sec-ch-ua headers to mimic real Chrome browser
        - Session pre-visits LinkedIn homepage to get cookies
        - Detects authwall/999 and stops gracefully instead of wasting time
        - Tries both the jobs-guest API and regular search page
        - Extracts JSON-LD in addition to DOM scraping
        """
        jobs    = []
        session = create_session()

        linkedin_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.linkedin.com/",
            "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
        }

        # Pre-visit to get cookies
        try:
            session.get("https://www.linkedin.com/", headers=linkedin_headers, timeout=TIMEOUT)
            time.sleep(1.5)
        except Exception:
            pass

        searches = [
            ("call center agent", "Philippines"),
            ("virtual assistant", "Philippines"),
            ("BPO customer service", "Philippines"),
            ("work from home Philippines", ""),
            ("accounting remote Philippines", ""),
            ("IT support Philippines", ""),
        ]

        blocked = False
        for keywords, location in searches:
            if blocked:
                break
            try:
                kw_enc  = requests.utils.quote(keywords)
                loc_enc = requests.utils.quote(location)

                # Try the public guest API first
                url = (
                    f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
                    f"keywords={kw_enc}&location={loc_enc}&f_TPR=r86400&sortBy=DD&start=0"
                )
                resp = session.get(url, headers=linkedin_headers, timeout=TIMEOUT)

                # If blocked, try the regular search page
                if resp.status_code == 999 or resp.status_code == 429:
                    url2 = (
                        f"https://www.linkedin.com/jobs/search?"
                        f"keywords={kw_enc}&location={loc_enc}&f_TPR=r86400&sortBy=DD"
                    )
                    resp = session.get(url2, headers=linkedin_headers, timeout=TIMEOUT)

                if resp.status_code not in (200, 201):
                    logger.debug(f"LinkedIn '{keywords}': HTTP {resp.status_code}")
                    time.sleep(2)
                    continue

                # Detect authwall — stop trying if hit
                if "authwall" in resp.url or "uas/login" in resp.url or "checkpoint" in resp.url:
                    logger.info("LinkedIn: Authwall detected — stopping LinkedIn scraper for this cycle")
                    blocked = True
                    break

                soup = BeautifulSoup(resp.text, "html.parser")

                # Check if we got a login page
                if soup.find("form", id="login"):
                    logger.info("LinkedIn: Got login form — stopping")
                    blocked = True
                    break

                # JSON-LD extraction
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

                # DOM scraping
                cards = (
                    soup.find_all("div", class_=re.compile(r"base-card|job-search-card|job-card", re.I))
                    or soup.find_all("li", class_=re.compile(r"result-card|jobs-search-results__list-item", re.I))
                )
                for card in cards[:10]:
                    title_el = card.find("h3") or card.find("h2") or card.find(class_=re.compile(r"job-title|position", re.I))
                    if not title_el:
                        continue
                    title   = title_el.get_text(strip=True)
                    a_el    = card.find("a", href=True)
                    link    = a_el["href"].split("?")[0] if a_el else ""
                    comp_el = card.find(class_=re.compile(r"company|subtitle", re.I)) or card.find("h4")
                    company = comp_el.get_text(strip=True) if comp_el else ""
                    loc_el  = card.find(class_=re.compile(r"location|locale", re.I))
                    job_loc = loc_el.get_text(strip=True) if loc_el else "Philippines"
                    if title and link and "linkedin.com" in link:
                        jobs.append(make_job(title, company, link, "LinkedIn", job_loc))

                time.sleep(2.0)  # LinkedIn needs a long delay
            except Exception as e:
                logger.debug(f"LinkedIn '{keywords}': {e}")

        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  6. JOBSTREET PH — Session-based with pre-visit cookies
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_jobstreet(self) -> List[Dict]:
        jobs    = []
        session = create_session()

        # Pre-visit to get session cookies — reduces 403s
        try:
            session.get("https://www.jobstreet.com.ph/", headers=get_headers(), timeout=TIMEOUT)
            time.sleep(0.8)
        except Exception:
            pass

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
                resp = session.get(url, headers=get_headers({"Referer": "https://www.jobstreet.com.ph/"}), timeout=TIMEOUT)
                if resp.status_code == 403:
                    time.sleep(1)
                    continue

                soup  = BeautifulSoup(resp.text, "html.parser")
                found = False

                # Method 1: JSON-LD
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
                                val  = sal_data.get("value", {})
                                curr = sal_data.get("currency", "PHP")
                                if isinstance(val, dict):
                                    mn = val.get("minValue")
                                    mx = val.get("maxValue")
                                    if mn and mx:
                                        salary = f"{curr} {int(mn):,}–{int(mx):,}"
                            if title and link:
                                jobs.append(make_job(title, company, link, "JobStreet PH", location, salary))
                                found = True
                    except Exception:
                        pass

                # Method 2: __NEXT_DATA__
                if not found:
                    next_data = soup.find("script", id="__NEXT_DATA__")
                    if next_data:
                        try:
                            data       = json.loads(next_data.string or "{}")
                            page_props = data.get("props", {}).get("pageProps", {})
                            job_list   = (
                                page_props.get("jobSearchResult", {}).get("jobs", [])
                                or page_props.get("jobs", [])
                                or page_props.get("initialData", {}).get("jobs", [])
                            )
                            for j in job_list[:15]:
                                title   = j.get("title", "") or (j.get("roleTitles") or [""])[0]
                                company = j.get("companyName", "") or j.get("advertiser", {}).get("description", "")
                                job_id  = j.get("id", "")
                                link    = f"https://www.jobstreet.com.ph/job/{job_id}" if job_id else ""
                                loc_l   = j.get("locationWhereYouCanWork", [{}])
                                location = loc_l[0].get("label", "Philippines") if loc_l else "Philippines"
                                if title and link:
                                    jobs.append(make_job(title, company, link, "JobStreet PH", location))
                        except Exception:
                            pass

                time.sleep(1.0)
            except Exception as e:
                logger.debug(f"JobStreet '{url}': {e}")

        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  7. ONLINEJOBS.PH
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_onlinejobs(self) -> List[Dict]:
        jobs    = []
        session = create_session()
        searches = [
            "virtual-assistant", "data-entry", "customer-service",
            "social-media", "bookkeeper", "content-writer", "graphic-designer",
        ]

        for kw in searches:
            try:
                url  = f"https://www.onlinejobs.ph/jobseekers/joblist/1?keyword={kw}&jobtype=1&category=0"
                resp = session.get(url, headers=get_headers(), timeout=TIMEOUT)
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
                                company = item.get("hiringOrganization", {}).get("name", "Remote Employer")
                                link    = item.get("url", "")
                                if title and link:
                                    jobs.append(make_job(title, company, link, "OnlineJobs.ph", "Philippines (Remote)"))
                    except Exception:
                        pass

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
    #  8. KALIBRR — Session + __NEXT_DATA__ fallback
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_kalibrr(self) -> List[Dict]:
        jobs    = []
        session = create_session()

        try:
            session.get("https://www.kalibrr.com/", headers=get_headers(), timeout=TIMEOUT)
            time.sleep(0.5)
        except Exception:
            pass

        searches = ["call+center", "virtual+assistant", "BPO", "customer+service", "work+from+home"]

        for kw in searches:
            try:
                url  = f"https://www.kalibrr.com/job-board/te/philippines?q={kw}&sort=recent"
                resp = session.get(url, headers=get_headers({"Referer": "https://www.kalibrr.com/"}), timeout=TIMEOUT)
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
                                loc_raw = item.get("jobLocation", {})
                                location = "Philippines"
                                if isinstance(loc_raw, dict):
                                    location = loc_raw.get("address", {}).get("addressLocality", "Philippines")
                                if title and link:
                                    jobs.append(make_job(title, company, link, "Kalibrr", location))
                    except Exception:
                        pass

                next_data = soup.find("script", id="__NEXT_DATA__")
                if next_data:
                    try:
                        data     = json.loads(next_data.string or "{}")
                        job_list = data.get("props", {}).get("pageProps", {}).get("jobs", [])
                        for j in job_list[:10]:
                            title   = j.get("title", "")
                            company = j.get("company", {}).get("name", "")
                            job_id  = j.get("id", "")
                            c_code  = j.get("company", {}).get("code", "")
                            link    = f"https://www.kalibrr.com/c/{c_code}/jobs/{job_id}" if job_id else ""
                            if title and link:
                                jobs.append(make_job(title, company, link, "Kalibrr"))
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
        jobs    = []
        session = create_session()
        searches = ["call+center", "virtual+assistant", "customer+service", "bpo"]

        for kw in searches:
            try:
                url  = f"https://ph.bossjob.com/jobs?search={kw}&sort=latest"
                resp = session.get(url, headers=get_headers(), timeout=TIMEOUT)
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
    #  10. TRABAHO.PH — FIXED URL format (tries multiple formats)
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_trabaho(self) -> List[Dict]:
        """BUG FIXED: Try multiple URL formats since trabaho.ph may have changed."""
        jobs    = []
        session = create_session()
        searches = ["call-center", "virtual-assistant", "bpo", "work-from-home", "customer-service"]

        for kw in searches:
            try:
                urls_to_try = [
                    f"https://trabaho.ph/jobs/{kw}",
                    f"https://trabaho.ph/search?q={kw}",
                    f"https://trabaho.ph/jobs?q={kw}&sort=newest",
                    f"https://trabaho.ph/?s={kw}",
                ]
                resp = None
                for url in urls_to_try:
                    try:
                        r = session.get(url, headers=get_headers(), timeout=TIMEOUT)
                        if r.status_code == 200:
                            resp = r
                            break
                    except Exception:
                        continue

                if not resp:
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

                for card in soup.find_all("div", class_=re.compile(r"job.?item|job.?listing|vacancy|job.?card", re.I))[:10]:
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
                    if title and link and is_relevant(title):
                        jobs.append(make_job(title, company, link, "Trabaho.ph", location))

                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"Trabaho '{kw}': {e}")

        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  11. GLASSDOOR PH
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_glassdoor(self) -> List[Dict]:
        jobs    = []
        session = create_session()
        searches = ["call-center", "virtual-assistant", "BPO", "customer-service"]

        for kw in searches:
            try:
                kw_len = len(kw)
                url  = f"https://www.glassdoor.com/Job/philippines-{kw}-jobs-SRCH_IL.0,11_IN194_KO12,{12+kw_len}.htm?sortBy=date_desc"
                resp = session.get(url, headers=get_headers({"Referer": "https://www.glassdoor.com/"}), timeout=TIMEOUT)
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
                                    val  = sal_data.get("value", {})
                                    curr = sal_data.get("currency", "PHP")
                                    if isinstance(val, dict):
                                        mn = val.get("minValue")
                                        mx = val.get("maxValue")
                                        if mn and mx:
                                            salary = f"{curr} {int(mn):,}–{int(mx):,}"
                                if title and link:
                                    jobs.append(make_job(title, company, link, "Glassdoor PH", "Philippines", salary))
                    except Exception:
                        pass
                time.sleep(1.0)
            except Exception as e:
                logger.debug(f"Glassdoor '{kw}': {e}")
        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  12. MONSTER PH — Tries both .com.ph and .com
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_monster(self) -> List[Dict]:
        jobs    = []
        session = create_session()
        searches = ["call-center", "virtual-assistant", "bpo", "customer-service"]

        for kw in searches:
            try:
                urls = [
                    f"https://www.monster.com.ph/jobs/search/?q={kw}&where=Philippines&sort=dt.desc",
                    f"https://www.monster.com/jobs/search?q={kw}&where=Philippines&sort=dt.desc",
                ]
                resp = None
                for url in urls:
                    try:
                        r = session.get(url, headers=get_headers(), timeout=TIMEOUT)
                        if r.status_code == 200:
                            resp = r
                            break
                    except Exception:
                        continue

                if not resp:
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
                                    jobs.append(make_job(title, company, link, "Monster PH"))
                    except Exception:
                        pass

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

    # ═══════════════════════════════════════════════════════════════════════════
    #  13. UPWORK — FIXED RSS URL (old format was broken)
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_upwork(self) -> List[Dict]:
        """BUG FIXED: Upwork RSS URL format updated. Added fallback to search page."""
        jobs    = []
        session = create_session()
        rss_searches = [
            "virtual+assistant", "customer+service", "data+entry",
            "social+media+manager", "bookkeeper", "content+writer",
        ]

        for term in rss_searches:
            try:
                # FIX: Try multiple URL formats
                rss_urls = [
                    f"https://www.upwork.com/ab/feed/jobs/rss?q={term}&sort=recency&paging=0%3B10&api_params=1",
                    f"https://www.upwork.com/ab/feed/jobs/rss?q={term}&sort=recency",
                    f"https://www.upwork.com/api/feed/v1/vacancies/search.rss?q={term}",
                ]
                resp = None
                for rss_url in rss_urls:
                    try:
                        r = session.get(rss_url, headers=get_headers({
                            "Accept": "application/rss+xml, application/xml, text/xml, */*",
                        }), timeout=TIMEOUT)
                        if r.status_code == 200 and ("<rss" in r.text[:500] or "<feed" in r.text[:500]):
                            resp = r
                            break
                    except Exception:
                        continue

                if not resp:
                    continue

                root    = ET.fromstring(resp.content)
                channel = root.find("channel") or root
                items   = channel.findall("item")
                for item in items[:15]:
                    title = item.findtext("title", "")
                    link  = item.findtext("link", "")
                    desc  = item.findtext("description", "")
                    if title and link and is_relevant(title, desc):
                        salary = None
                        m = re.search(r"Budget:\s*\$?([\d,]+(?:\s*[-–]\s*\$?[\d,]+)?)", desc)
                        if m:
                            salary = f"${m.group(1)}"
                        jobs.append(make_job(title, "Upwork Client", link, "Upwork", "Remote (Worldwide)", salary, desc))
                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"Upwork RSS '{term}': {e}")
        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  14. FREELANCER.COM — FIXED RSS URL with fallback
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_freelancer(self) -> List[Dict]:
        """BUG FIXED: Freelancer.com RSS URL format updated with web scrape fallback."""
        jobs    = []
        session = create_session()
        searches = ["virtual-assistant", "customer-service", "data-entry", "social-media", "content-writing"]

        for kw in searches:
            try:
                rss_urls = [
                    f"https://www.freelancer.com/rss/search/{kw}.xml",
                    f"https://www.freelancer.com/rss/jobs/{kw}",
                ]
                resp = None
                for rss_url in rss_urls:
                    try:
                        r = session.get(rss_url, headers=get_headers({
                            "Accept": "application/rss+xml, application/xml, text/xml",
                        }), timeout=TIMEOUT)
                        if r.status_code == 200 and ("<rss" in r.text[:500] or "<feed" in r.text[:500]):
                            resp = r
                            break
                    except Exception:
                        continue

                if resp:
                    root = ET.fromstring(resp.content)
                    channel = root.find("channel") or root
                    for item in (channel.findall("item") or [])[:15]:
                        title = item.findtext("title", "")
                        link  = item.findtext("link", "")
                        desc  = item.findtext("description", "")
                        if title and link and is_relevant(title, desc):
                            salary = None
                            m = re.search(r"\$([\d,]+(?:\s*[-–]\s*[\d,]+)?)", title + " " + desc)
                            if m:
                                salary = f"${m.group(1)}"
                            jobs.append(make_job(title, "Freelancer Client", link, "Freelancer.com", "Remote (Worldwide)", salary, desc))
                else:
                    # Fallback: web scrape
                    url  = f"https://www.freelancer.com/jobs/{kw}/"
                    resp = session.get(url, headers=get_headers(), timeout=TIMEOUT)
                    if resp and resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        for card in soup.find_all("div", class_=re.compile(r"JobSearchCard|job-item", re.I))[:10]:
                            a = card.find("a", href=True)
                            if not a:
                                continue
                            title = a.get_text(strip=True)
                            href  = a["href"]
                            link  = "https://www.freelancer.com" + href if href.startswith("/") else href
                            desc_el = card.find(class_=re.compile(r"description|summary", re.I))
                            desc    = desc_el.get_text(strip=True) if desc_el else ""
                            if title and link and is_relevant(title, desc):
                                jobs.append(make_job(title, "Freelancer Client", link, "Freelancer.com", "Remote (Worldwide)"))

                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"Freelancer.com '{kw}': {e}")
        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  15. JOBSDB PH
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_jobsdb(self) -> List[Dict]:
        jobs    = []
        session = create_session()
        searches = ["call-center", "virtual-assistant", "bpo", "customer-service"]

        for kw in searches:
            try:
                url  = f"https://ph.jobsdb.com/ph/search-jobs/{kw}/1?sortMode=1"
                resp = session.get(url, headers=get_headers({"Referer": "https://ph.jobsdb.com/"}), timeout=TIMEOUT)
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
                                        mn = val.get("minValue")
                                        mx = val.get("maxValue")
                                        if mn:
                                            salary = f"PHP {int(mn):,}–{int(mx):,}" if mx else f"PHP {int(mn):,}+"
                                if title and link:
                                    jobs.append(make_job(title, company, link, "JobsDB PH", "Philippines", salary))
                    except Exception:
                        pass

                next_data = soup.find("script", id="__NEXT_DATA__")
                if next_data:
                    try:
                        data     = json.loads(next_data.string or "{}")
                        job_list = data.get("props", {}).get("pageProps", {}).get("jobs", [])
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

    # ═══════════════════════════════════════════════════════════════════════════
    #  16. OLX PH JOBS
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_olx(self) -> List[Dict]:
        jobs    = []
        session = create_session()
        searches = ["call-center", "bpo", "virtual-assistant", "customer-service", "work-from-home"]

        for kw in searches:
            try:
                url  = f"https://www.olx.ph/jobs/?search%5Bfilter_str_category%5D=jobs&search%5Bq%5D={kw.replace('-', '+')}&s=newest_first"
                resp = session.get(url, headers=get_headers(), timeout=TIMEOUT)
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
                                company = item.get("hiringOrganization", {}).get("name", "OLX Poster") if item.get("@type") == "JobPosting" else "OLX Poster"
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

    # ═══════════════════════════════════════════════════════════════════════════
    #  17. GOOGLE JOBS via SerpAPI (optional)
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_google_jobs(self) -> List[Dict]:
        """Set SERPAPI_KEY in Railway env to enable. Free at serpapi.com"""
        API_KEY = os.environ.get("SERPAPI_KEY", "")
        if not API_KEY:
            return []

        jobs = []
        searches = [
            "call center jobs Philippines",
            "virtual assistant jobs Philippines",
            "BPO jobs Philippines",
            "work from home jobs Philippines",
        ]
        for q in searches:
            try:
                resp = requests.get(
                    "https://serpapi.com/search",
                    params={"engine": "google_jobs", "q": q, "location": "Philippines", "api_key": API_KEY, "chips": "date_posted:today"},
                    timeout=TIMEOUT,
                )
                data = resp.json()
                for j in data.get("jobs_results", []):
                    title    = j.get("title", "")
                    company  = j.get("company_name", "")
                    location = j.get("location", "Philippines")
                    link     = j.get("related_links", [{}])[0].get("link", "") or j.get("share_link", "")
                    sal_data = j.get("detected_extensions", {})
                    salary   = sal_data.get("salary") if sal_data else None
                    if title and link:
                        jobs.append(make_job(title, company, link, "Google Jobs", location, salary))
                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"Google Jobs '{q}': {e}")
        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  18. TELEGRAM PUBLIC JOB CHANNELS
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_telegram_channels(self) -> List[Dict]:
        jobs    = []
        session = create_session()
        channels = [
            "PHJobHunters", "PHJobVacancy", "jobshiringph",
            "PHJobsOnline", "bpojobsph", "virtualassistantph",
        ]

        for channel in channels:
            try:
                url  = f"https://t.me/s/{channel}"
                resp = session.get(url, headers=get_headers({"Accept": "text/html"}), timeout=TIMEOUT)
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")

                for msg in soup.find_all("div", class_="tgme_widget_message_text")[:20]:
                    text = msg.get_text(separator=" ", strip=True)
                    if not text or len(text) < 30 or not is_relevant(text[:200]):
                        continue
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    title = ""
                    for line in lines[:3]:
                        if any(kw.lower() in line.lower() for kw in ["hiring", "looking for", "vacancy", "job", "position", "needed"]):
                            title = line[:100]
                            break
                    if not title and lines:
                        title = lines[0][:100]
                    if not title:
                        continue
                    link_el  = msg.find_parent("div", class_="tgme_widget_message")
                    msg_link = ""
                    if link_el:
                        data_post = link_el.get("data-post", "")
                        if data_post:
                            msg_link = f"https://t.me/{data_post}"
                    if not msg_link:
                        msg_link = f"https://t.me/s/{channel}"
                    company = ""
                    m = re.search(r"(?:company|employer|client):\s*(.+?)(?:\n|$)", text, re.I)
                    if m:
                        company = m.group(1).strip()[:80]
                    salary = None
                    m2 = re.search(r"(?:salary|pay|rate|compensation):\s*(.+?)(?:\n|$)", text, re.I)
                    if m2:
                        salary = m2.group(1).strip()[:60]
                    jobs.append(make_job(title, company or f"@{channel}", msg_link, "Telegram PH Jobs", "Philippines", salary, text[:300]))

                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"Telegram channel '@{channel}': {e}")

        return jobs
