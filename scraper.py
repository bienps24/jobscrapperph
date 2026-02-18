"""
PH Job Scraper — 10+ sources
Sources:
  1. Indeed PH          (RSS feed)
  2. JobStreet PH       (web scrape)
  3. OnlineJobs.ph      (web scrape)
  4. Jooble             (API + web scrape fallback)
  5. Kalibrr            (web scrape + JSON-LD)
  6. LinkedIn PH        (public job search)
  7. Trabaho.ph         (web scrape)
  8. BossJob PH         (web scrape)
  9. PhilJobNet (DOLE)  (RSS feed)
 10. RemoteOK           (API - remote jobs)
 11. Jobspayingshoutout (social/community)
"""

import asyncio
import json
import logging
import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fil;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

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


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip() if text else ""


def make_job(title, company, link, source, location="Philippines", salary=None, description="") -> Dict:
    return {
        "title": clean_text(title),
        "company": clean_text(company) if company else "Hindi nabanggit",
        "link": link.strip() if link else "",
        "category": detect_category(title, description),
        "location": clean_text(location) if location else "Philippines",
        "salary": clean_text(salary) if salary else None,
        "source": source,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN SCRAPER CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class JobScraper:

    async def scrape_all(self) -> List[Dict]:
        scrapers = [
            self.scrape_indeed_rss,
            self.scrape_jobstreet,
            self.scrape_onlinejobs,
            self.scrape_jooble,
            self.scrape_kalibrr,
            self.scrape_linkedin,
            self.scrape_trabaho_ph,
            self.scrape_bossjob,
            self.scrape_philjobnet,
            self.scrape_remoteok,
        ]

        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(None, fn) for fn in scrapers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_jobs = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Scraper {scrapers[i].__name__} failed: {result}")
            elif isinstance(result, list):
                logger.info(f"✅ {scrapers[i].__name__}: {len(result)} jobs")
                all_jobs.extend(result)

        # Deduplicate by link
        seen = set()
        unique = []
        for job in all_jobs:
            link = job.get("link", "")
            if link and link not in seen:
                seen.add(link)
                unique.append(job)

        # Filter only relevant jobs
        relevant = [j for j in unique if is_relevant(j.get("title", ""))]
        logger.info(f"📊 Total: {len(all_jobs)} scraped → {len(unique)} unique → {len(relevant)} relevant")
        return relevant

    # ═══════════════════════════════════════════════════════════════════════════
    #  1. INDEED PH — RSS Feed
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_indeed_rss(self) -> List[Dict]:
        jobs = []
        search_terms = [
            "call+center", "virtual+assistant", "BPO",
            "work+from+home", "online+gaming+POGO",
            "customer+service", "accounting+philippines",
            "IT+support+philippines", "sales+representative",
        ]
        for term in search_terms:
            try:
                url = f"https://ph.indeed.com/rss?q={term}&l=Philippines&sort=date&limit=20"
                resp = requests.get(url, headers=HEADERS, timeout=15)
                root = ET.fromstring(resp.content)
                channel = root.find("channel")
                if not channel:
                    continue
                ns = "https://www.indeed.com/about/"
                for item in channel.findall("item"):
                    title = item.findtext("title", "")
                    link = item.findtext("link", "")
                    desc = item.findtext("description", "")
                    company_el = item.find(f"{{{ns}}}company")
                    company = company_el.text if company_el is not None else ""
                    city_el = item.find(f"{{{ns}}}city")
                    state_el = item.find(f"{{{ns}}}state")
                    location = ", ".join(filter(None, [
                        city_el.text if city_el is not None else "",
                        state_el.text if state_el is not None else "",
                    ])) or "Philippines"
                    salary_el = item.find(f"{{{ns}}}salary")
                    salary = salary_el.text if salary_el is not None else None
                    if title and link:
                        jobs.append(make_job(title, company, link, "Indeed PH", location, salary, desc))
            except Exception as e:
                logger.debug(f"Indeed RSS '{term}': {e}")
        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  2. JOBSTREET PH — Web Scrape
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_jobstreet(self) -> List[Dict]:
        jobs = []
        categories = [
            "call-center-jobs", "bpo-jobs", "virtual-assistant-jobs",
            "customer-service-jobs", "work-from-home-jobs",
            "information-technology-jobs", "accounting-jobs",
            "sales-jobs", "marketing-jobs", "healthcare-nursing-jobs",
        ]
        for cat in categories:
            try:
                url = f"https://www.jobstreet.com.ph/{cat}"
                resp = requests.get(url, headers=HEADERS, timeout=15)
                soup = BeautifulSoup(resp.text, "html.parser")

                # Try JSON-LD structured data first (most reliable)
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data = json.loads(script.string or "[]")
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get("@type") == "JobPosting":
                                title = item.get("title", "")
                                company = item.get("hiringOrganization", {}).get("name", "")
                                link = item.get("url", item.get("sameAs", ""))
                                location = item.get("jobLocation", {})
                                if isinstance(location, dict):
                                    location = location.get("address", {}).get("addressLocality", "Philippines")
                                salary_data = item.get("baseSalary", {})
                                salary = None
                                if isinstance(salary_data, dict):
                                    val = salary_data.get("value", {})
                                    if isinstance(val, dict):
                                        mn = val.get("minValue", "")
                                        mx = val.get("maxValue", "")
                                        curr = salary_data.get("currency", "PHP")
                                        if mn and mx:
                                            salary = f"{curr} {mn:,}–{mx:,}"
                                if title and link:
                                    jobs.append(make_job(title, company, link, "JobStreet PH", str(location), salary))
                    except Exception:
                        pass

                # Fallback: article cards
                if not jobs:
                    cards = soup.find_all("article") or soup.find_all("div", class_=re.compile(r"job.?card", re.I))
                    for card in cards[:15]:
                        a = card.find("a", href=True)
                        title_el = card.find(["h1", "h2", "h3"])
                        if not (a and title_el):
                            continue
                        title = title_el.get_text(strip=True)
                        link = a["href"]
                        if not link.startswith("http"):
                            link = "https://www.jobstreet.com.ph" + link
                        comp_el = card.find(class_=re.compile(r"company|employer", re.I))
                        company = comp_el.get_text(strip=True) if comp_el else ""
                        jobs.append(make_job(title, company, link, "JobStreet PH"))
            except Exception as e:
                logger.debug(f"JobStreet '{cat}': {e}")
        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  3. ONLINEJOBS.PH — Best for VA & Remote
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_onlinejobs(self) -> List[Dict]:
        jobs = []
        keywords = [
            "virtual-assistant", "data-entry", "customer-service",
            "social-media-manager", "bookkeeper", "content-writer",
            "graphic-designer", "web-developer", "project-manager",
        ]
        for kw in keywords:
            try:
                url = f"https://www.onlinejobs.ph/jobseekers/joblist/1?keyword={kw}"
                resp = requests.get(url, headers=HEADERS, timeout=15)
                soup = BeautifulSoup(resp.text, "html.parser")

                for card in soup.find_all("div", class_=re.compile(r"job.?post|jobpost", re.I))[:12]:
                    title_el = card.find(["h2", "h3", "a"])
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    a_el = card.find("a", href=True)
                    link = a_el["href"] if a_el else ""
                    if link and not link.startswith("http"):
                        link = "https://www.onlinejobs.ph" + link
                    comp_el = card.find(class_=re.compile(r"company|employer|client", re.I))
                    company = comp_el.get_text(strip=True) if comp_el else "Remote Employer"
                    rate_el = card.find(class_=re.compile(r"rate|salary|pay", re.I))
                    salary = rate_el.get_text(strip=True) if rate_el else None
                    if title and link:
                        jobs.append(make_job(title, company, link, "OnlineJobs.ph", "Philippines (Remote)", salary))
            except Exception as e:
                logger.debug(f"OnlineJobs '{kw}': {e}")
        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  4. JOOBLE — API + Scrape Fallback
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_jooble(self) -> List[Dict]:
        import os
        API_KEY = os.environ.get("JOOBLE_API_KEY", "")
        jobs = []
        search_terms = [
            "call center", "virtual assistant", "BPO",
            "work from home", "POGO online gaming",
            "customer service", "accounting", "IT support",
        ]
        for term in search_terms:
            try:
                if API_KEY:
                    resp = requests.post(
                        f"https://jooble.org/api/{API_KEY}",
                        json={"keywords": term, "location": "Philippines", "page": 1},
                        headers={"Content-Type": "application/json"},
                        timeout=15,
                    )
                    data = resp.json()
                    for j in data.get("jobs", []):
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
                    url = f"https://ph.jooble.org/SearchResult?ukw={term.replace(' ', '+')}"
                    resp = requests.get(url, headers=HEADERS, timeout=15)
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for card in soup.find_all("article")[:10]:
                        title_el = card.find(["h2", "h3", "a"])
                        if not title_el:
                            continue
                        title = title_el.get_text(strip=True)
                        a_el = card.find("a", href=True)
                        link = a_el["href"] if a_el else ""
                        if link and not link.startswith("http"):
                            link = "https://ph.jooble.org" + link
                        comp_el = card.find(class_=re.compile(r"company|employer", re.I))
                        company = comp_el.get_text(strip=True) if comp_el else ""
                        if title and link:
                            jobs.append(make_job(title, company, link, "Jooble"))
            except Exception as e:
                logger.debug(f"Jooble '{term}': {e}")
        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  5. KALIBRR — JSON-LD + Web Scrape
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_kalibrr(self) -> List[Dict]:
        jobs = []
        keywords = [
            "call+center", "virtual+assistant", "BPO",
            "remote+work", "customer+service", "accounting",
        ]
        for kw in keywords:
            try:
                url = f"https://www.kalibrr.com/job-board/te/philippines?q={kw}&sort=recent"
                resp = requests.get(url, headers=HEADERS, timeout=15)
                soup = BeautifulSoup(resp.text, "html.parser")

                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data = json.loads(script.string or "{}")
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get("@type") == "JobPosting":
                                title = item.get("title", "")
                                company = item.get("hiringOrganization", {}).get("name", "")
                                link = item.get("url", "")
                                location = "Philippines"
                                loc_data = item.get("jobLocation", {})
                                if isinstance(loc_data, dict):
                                    addr = loc_data.get("address", {})
                                    location = addr.get("addressLocality", "Philippines")
                                if title and link:
                                    jobs.append(make_job(title, company, link, "Kalibrr", location))
                    except Exception:
                        pass

                # Fallback: card scraping
                for card in soup.find_all("div", class_=re.compile(r"job.?card|k-job", re.I))[:10]:
                    a = card.find("a", href=True)
                    title_el = card.find(["h2", "h3"])
                    if not (a and title_el):
                        continue
                    title = title_el.get_text(strip=True)
                    link = a["href"]
                    if not link.startswith("http"):
                        link = "https://www.kalibrr.com" + link
                    comp_el = card.find(class_=re.compile(r"company|employer", re.I))
                    company = comp_el.get_text(strip=True) if comp_el else ""
                    jobs.append(make_job(title, company, link, "Kalibrr"))
            except Exception as e:
                logger.debug(f"Kalibrr '{kw}': {e}")
        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  6. LINKEDIN — Public Job Search (No Login Required)
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_linkedin(self) -> List[Dict]:
        jobs = []
        # LinkedIn public job search — no login needed for viewing listings
        search_configs = [
            ("call center", "Philippines"),
            ("virtual assistant", "Philippines"),
            ("BPO customer service", "Philippines"),
            ("work from home Philippines", ""),
            ("POGO online gaming", "Philippines"),
            ("accounting remote Philippines", ""),
            ("IT support Philippines", ""),
        ]
        for keywords, location in search_configs:
            try:
                kw_encoded = keywords.replace(" ", "%20")
                loc_encoded = location.replace(" ", "%20")
                url = (
                    f"https://www.linkedin.com/jobs/search?"
                    f"keywords={kw_encoded}&location={loc_encoded}"
                    f"&f_TPR=r86400&sortBy=DD"  # last 24 hours, sorted by date
                )
                resp = requests.get(url, headers={
                    **HEADERS,
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                }, timeout=15)
                soup = BeautifulSoup(resp.text, "html.parser")

                # LinkedIn job cards
                cards = soup.find_all("div", class_=re.compile(r"base-card|job-search-card", re.I))
                if not cards:
                    cards = soup.find_all("li", class_=re.compile(r"result-card|jobs-search", re.I))

                for card in cards[:10]:
                    title_el = card.find(["h3", "h2"], class_=re.compile(r"title|job.?title", re.I))
                    if not title_el:
                        title_el = card.find(["h3", "h2"])
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)

                    a_el = card.find("a", href=True)
                    link = a_el["href"] if a_el else ""
                    # Clean LinkedIn tracking params
                    if "?" in link:
                        link = link.split("?")[0]

                    comp_el = card.find(class_=re.compile(r"company|subtitle|employer", re.I))
                    company = comp_el.get_text(strip=True) if comp_el else ""

                    loc_el = card.find(class_=re.compile(r"location|locale", re.I))
                    job_location = loc_el.get_text(strip=True) if loc_el else "Philippines"

                    if title and link and "linkedin.com" in link:
                        jobs.append(make_job(title, company, link, "LinkedIn", job_location))
            except Exception as e:
                logger.debug(f"LinkedIn '{keywords}': {e}")
        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  7. TRABAHO.PH — Local PH Job Board
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_trabaho_ph(self) -> List[Dict]:
        jobs = []
        search_terms = ["call-center", "virtual-assistant", "bpo", "work-from-home", "accounting"]
        for term in search_terms:
            try:
                url = f"https://trabaho.ph/jobs?q={term}&l=&sort=newest"
                resp = requests.get(url, headers=HEADERS, timeout=15)
                soup = BeautifulSoup(resp.text, "html.parser")

                for card in soup.find_all("div", class_=re.compile(r"job.?item|job.?listing|vacancy", re.I))[:10]:
                    title_el = card.find(["h2", "h3", "a"])
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    a_el = card.find("a", href=True)
                    link = a_el["href"] if a_el else ""
                    if link and not link.startswith("http"):
                        link = "https://trabaho.ph" + link
                    comp_el = card.find(class_=re.compile(r"company|employer", re.I))
                    company = comp_el.get_text(strip=True) if comp_el else ""
                    loc_el = card.find(class_=re.compile(r"location|city", re.I))
                    location = loc_el.get_text(strip=True) if loc_el else "Philippines"
                    if title and link:
                        jobs.append(make_job(title, company, link, "Trabaho.ph", location))
            except Exception as e:
                logger.debug(f"Trabaho.ph '{term}': {e}")
        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  8. BOSSJOB PH — Growing PH Job Platform
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_bossjob(self) -> List[Dict]:
        jobs = []
        search_terms = [
            "call center", "virtual assistant", "bpo",
            "customer service", "work from home",
        ]
        for term in search_terms:
            try:
                url = f"https://ph.bossjob.com/jobs?search={term.replace(' ', '+')}&sort=latest"
                resp = requests.get(url, headers=HEADERS, timeout=15)
                soup = BeautifulSoup(resp.text, "html.parser")

                # Try JSON-LD
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data = json.loads(script.string or "{}")
                        if data.get("@type") == "JobPosting":
                            title = data.get("title", "")
                            company = data.get("hiringOrganization", {}).get("name", "")
                            link = data.get("url", "")
                            salary_data = data.get("baseSalary", {})
                            salary = None
                            if isinstance(salary_data, dict):
                                val = salary_data.get("value", {})
                                if isinstance(val, dict):
                                    mn = val.get("minValue", "")
                                    mx = val.get("maxValue", "")
                                    if mn:
                                        salary = f"PHP {mn:,}–{mx:,}" if mx else f"PHP {mn:,}+"
                            if title and link:
                                jobs.append(make_job(title, company, link, "BossJob PH", "Philippines", salary))
                    except Exception:
                        pass

                # Card fallback
                for card in soup.find_all("div", class_=re.compile(r"job.?card|position.?card", re.I))[:10]:
                    title_el = card.find(["h2", "h3", "span"], class_=re.compile(r"title|name|position", re.I))
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    a_el = card.find("a", href=True)
                    link = a_el["href"] if a_el else ""
                    if link and not link.startswith("http"):
                        link = "https://ph.bossjob.com" + link
                    comp_el = card.find(class_=re.compile(r"company|employer", re.I))
                    company = comp_el.get_text(strip=True) if comp_el else ""
                    sal_el = card.find(class_=re.compile(r"salary|pay|compensation", re.I))
                    salary = sal_el.get_text(strip=True) if sal_el else None
                    if title and link:
                        jobs.append(make_job(title, company, link, "BossJob PH", "Philippines", salary))
            except Exception as e:
                logger.debug(f"BossJob '{term}': {e}")
        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  9. PHILJOBNNET (DOLE) — Official Government Job Board
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_philjobnet(self) -> List[Dict]:
        jobs = []
        try:
            # PhilJobNet public job search
            url = "https://www.philjobnet.gov.ph/rss/jobs"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                channel = root.find("channel")
                if channel:
                    for item in channel.findall("item")[:30]:
                        title = item.findtext("title", "")
                        link = item.findtext("link", "")
                        desc = item.findtext("description", "")
                        if title and link and is_relevant(title, desc):
                            # Extract company from description
                            soup = BeautifulSoup(desc, "html.parser")
                            desc_text = soup.get_text()
                            company = ""
                            m = re.search(r"Company:\s*(.+?)(?:\n|$)", desc_text)
                            if m:
                                company = m.group(1).strip()
                            location = "Philippines"
                            m2 = re.search(r"Location:\s*(.+?)(?:\n|$)", desc_text)
                            if m2:
                                location = m2.group(1).strip()
                            jobs.append(make_job(title, company, link, "PhilJobNet", location))
        except Exception as e:
            logger.debug(f"PhilJobNet: {e}")

        # Fallback: scrape directly
        if not jobs:
            try:
                keywords = ["call center", "virtual assistant", "BPO", "customer service"]
                for kw in keywords:
                    url = f"https://www.philjobnet.gov.ph/jobs?q={kw.replace(' ', '+')}"
                    resp = requests.get(url, headers=HEADERS, timeout=15)
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for card in soup.find_all("div", class_=re.compile(r"job.?item|vacancy", re.I))[:8]:
                        title_el = card.find(["h2", "h3", "a"])
                        if not title_el:
                            continue
                        title = title_el.get_text(strip=True)
                        a_el = card.find("a", href=True)
                        link = a_el["href"] if a_el else ""
                        if link and not link.startswith("http"):
                            link = "https://www.philjobnet.gov.ph" + link
                        comp_el = card.find(class_=re.compile(r"company|employer", re.I))
                        company = comp_el.get_text(strip=True) if comp_el else ""
                        if title and link:
                            jobs.append(make_job(title, company, link, "PhilJobNet"))
            except Exception as e:
                logger.debug(f"PhilJobNet fallback: {e}")
        return jobs

    # ═══════════════════════════════════════════════════════════════════════════
    #  10. REMOTEOK — Best for Remote/WFH Jobs (JSON API)
    # ═══════════════════════════════════════════════════════════════════════════
    def scrape_remoteok(self) -> List[Dict]:
        jobs = []
        try:
            url = "https://remoteok.com/api"
            resp = requests.get(url, headers={
                **HEADERS,
                "Accept": "application/json",
            }, timeout=15)
            data = resp.json()

            # First item is legal disclaimer, skip it
            if isinstance(data, list) and len(data) > 1:
                for job in data[1:50]:  # check first 50 listings
                    title = job.get("position", "")
                    company = job.get("company", "")
                    link = job.get("url", "")
                    tags = job.get("tags", [])
                    description = job.get("description", "")
                    salary_min = job.get("salary_min")
                    salary_max = job.get("salary_max")
                    salary = None
                    if salary_min and salary_max:
                        salary = f"${salary_min:,}–${salary_max:,}/yr"
                    elif salary_min:
                        salary = f"${salary_min:,}+/yr"

                    # Check if Philippines-relevant or in relevant job categories
                    tag_text = " ".join(tags).lower()
                    full_text = title + " " + description + " " + tag_text
                    if is_relevant(title, tag_text):
                        jobs.append(make_job(
                            title, company, link, "RemoteOK",
                            "Remote (Worldwide)", salary, description[:200]
                        ))
        except Exception as e:
            logger.debug(f"RemoteOK: {e}")
        return jobs
