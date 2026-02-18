import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from typing import List, Dict

import requests

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ─────────────────────────────────────────────
#  KEYWORD CONFIG
# ─────────────────────────────────────────────

CALL_CENTER_KEYWORDS = [
    "call center", "customer service", "customer support", "BPO",
    "technical support", "CSR", "contact center", "helpdesk",
    "inbound", "outbound", "collections", "telemarketer",
]

VA_KEYWORDS = [
    "virtual assistant", "VA", "admin assistant", "administrative assistant",
    "data entry", "online assistant", "remote assistant", "executive assistant",
    "social media manager", "content moderator", "chat support",
]

POGO_KEYWORDS = [
    "POGO", "online gaming", "gaming operator", "casino dealer",
    "live dealer", "casino staff", "igaming", "i-gaming",
    "online casino", "gaming company",
]

REMOTE_KEYWORDS = [
    "work from home", "WFH", "remote", "telecommute", "home based",
    "homebased", "online job", "freelance",
]

ALL_KEYWORDS = CALL_CENTER_KEYWORDS + VA_KEYWORDS + POGO_KEYWORDS + REMOTE_KEYWORDS


def detect_category(title: str, description: str = "") -> str:
    text = (title + " " + description).lower()

    for kw in POGO_KEYWORDS:
        if kw.lower() in text:
            return "POGO / Online Gaming"
    for kw in VA_KEYWORDS:
        if kw.lower() in text:
            return "Virtual Assistant"
    for kw in CALL_CENTER_KEYWORDS:
        if kw.lower() in text:
            return "Call Center / BPO"
    for kw in REMOTE_KEYWORDS:
        if kw.lower() in text:
            return "Remote / WFH"
    return "General"


def is_relevant_job(title: str, description: str = "") -> bool:
    text = (title + " " + description).lower()
    return any(kw.lower() in text for kw in ALL_KEYWORDS)


# ─────────────────────────────────────────────
#  SCRAPERS
# ─────────────────────────────────────────────

class JobScraper:

    async def scrape_all(self) -> List[Dict]:
        """Run all scrapers concurrently"""
        tasks = [
            self._run_safe(self.scrape_jooble),
            self._run_safe(self.scrape_indeed_rss),
            self._run_safe(self.scrape_ph_jobstreet_rss),
            self._run_safe(self.scrape_onlinejobs_rss),
            self._run_safe(self.scrape_jobsph_api),
        ]
        results = await asyncio.gather(*tasks)

        all_jobs = []
        for job_list in results:
            all_jobs.extend(job_list)

        # Deduplicate by link
        seen = set()
        unique_jobs = []
        for job in all_jobs:
            if job["link"] not in seen:
                seen.add(job["link"])
                unique_jobs.append(job)

        logger.info(f"Total unique jobs scraped: {len(unique_jobs)}")
        return unique_jobs

    async def _run_safe(self, func) -> List[Dict]:
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, func)
        except Exception as e:
            logger.error(f"Scraper {func.__name__} error: {e}")
            return []

    # ── JOOBLE API ─────────────────────────────────
    def scrape_jooble(self) -> List[Dict]:
        """Jooble - free job API, covers PH jobs"""
        import os
        JOOBLE_API_KEY = os.environ.get("JOOBLE_API_KEY", "")

        jobs = []
        keywords_to_search = [
            "call center Philippines",
            "virtual assistant Philippines",
            "BPO Philippines",
            "work from home Philippines",
            "online gaming Philippines",
        ]

        for keyword in keywords_to_search:
            try:
                url = f"https://jooble.org/api/{JOOBLE_API_KEY}" if JOOBLE_API_KEY else None

                if not JOOBLE_API_KEY:
                    # Fallback: scrape Jooble without API
                    jobs.extend(self._scrape_jooble_no_api(keyword))
                    continue

                payload = {
                    "keywords": keyword,
                    "location": "Philippines",
                    "page": 1,
                }
                resp = requests.post(url, json=payload, headers=HEADERS, timeout=15)
                data = resp.json()

                for j in data.get("jobs", []):
                    title = j.get("title", "")
                    if not is_relevant_job(title):
                        continue
                    jobs.append({
                        "title": title,
                        "company": j.get("company", "Unknown Company"),
                        "link": j.get("link", ""),
                        "category": detect_category(title, j.get("snippet", "")),
                        "location": j.get("location", "Philippines"),
                        "source": "Jooble",
                    })
            except Exception as e:
                logger.error(f"Jooble error for '{keyword}': {e}")

        return jobs

    def _scrape_jooble_no_api(self, keyword: str) -> List[Dict]:
        """Scrape Jooble website directly if no API key"""
        from bs4 import BeautifulSoup
        jobs = []
        try:
            url = f"https://ph.jooble.org/SearchResult?ukw={keyword.replace(' ', '+')}"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            articles = soup.find_all("article") or soup.find_all("div", {"data-test": "job-card"})

            for article in articles[:10]:
                title_el = article.find(["h2", "h3", "a"])
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if not is_relevant_job(title):
                    continue

                link_el = article.find("a", href=True)
                link = link_el["href"] if link_el else ""
                if link and not link.startswith("http"):
                    link = "https://ph.jooble.org" + link

                company_el = article.find(["span", "div"], class_=re.compile(r"company|employer", re.I))
                company = company_el.get_text(strip=True) if company_el else "Unknown"

                jobs.append({
                    "title": title,
                    "company": company,
                    "link": link,
                    "category": detect_category(title),
                    "location": "Philippines",
                    "source": "Jooble",
                })
        except Exception as e:
            logger.error(f"Jooble no-api error: {e}")
        return jobs

    # ── INDEED RSS ─────────────────────────────────
    def scrape_indeed_rss(self) -> List[Dict]:
        """Indeed Philippines RSS Feed"""
        jobs = []
        search_terms = [
            "call+center",
            "virtual+assistant",
            "BPO+customer+service",
            "work+from+home",
            "online+gaming",
        ]

        for term in search_terms:
            try:
                url = (
                    f"https://ph.indeed.com/rss?q={term}"
                    f"&l=Philippines&sort=date&limit=15"
                )
                resp = requests.get(url, headers=HEADERS, timeout=15)
                root = ET.fromstring(resp.content)

                channel = root.find("channel")
                if not channel:
                    continue

                for item in channel.findall("item"):
                    title = item.findtext("title", "")
                    link = item.findtext("link", "")
                    company_tag = item.find("{https://www.indeed.com/about/}company")
                    company = company_tag.text if company_tag is not None else "Unknown"
                    location_tag = item.find("{https://www.indeed.com/about/}city")
                    location = location_tag.text if location_tag is not None else "Philippines"

                    description = item.findtext("description", "")

                    if not is_relevant_job(title, description):
                        continue

                    jobs.append({
                        "title": title,
                        "company": company,
                        "link": link,
                        "category": detect_category(title, description),
                        "location": location,
                        "source": "Indeed PH",
                    })
            except Exception as e:
                logger.error(f"Indeed RSS error for '{term}': {e}")

        return jobs

    # ── JOBSTREET RSS ──────────────────────────────
    def scrape_ph_jobstreet_rss(self) -> List[Dict]:
        """JobStreet Philippines via scraping"""
        from bs4 import BeautifulSoup
        jobs = []

        search_keywords = [
            "call-center-jobs",
            "virtual-assistant-jobs",
            "bpo-jobs",
            "customer-service-jobs",
            "work-from-home-jobs",
        ]

        for keyword in search_keywords:
            try:
                url = f"https://www.jobstreet.com.ph/{keyword}"
                resp = requests.get(url, headers=HEADERS, timeout=15)
                soup = BeautifulSoup(resp.text, "html.parser")

                # JobStreet job cards
                job_cards = soup.find_all("article", attrs={"data-search-sol-meta": True})
                if not job_cards:
                    job_cards = soup.find_all("div", class_=re.compile(r"job-card|jobCard", re.I))

                for card in job_cards[:10]:
                    title_el = card.find(["h1", "h2", "h3", "a"], class_=re.compile(r"title|position", re.I))
                    if not title_el:
                        title_el = card.find("a")
                    if not title_el:
                        continue

                    title = title_el.get_text(strip=True)
                    if not title or not is_relevant_job(title):
                        continue

                    link_el = card.find("a", href=True)
                    link = link_el["href"] if link_el else ""
                    if link and not link.startswith("http"):
                        link = "https://www.jobstreet.com.ph" + link

                    company_el = card.find(class_=re.compile(r"company|employer", re.I))
                    company = company_el.get_text(strip=True) if company_el else "Unknown"

                    location_el = card.find(class_=re.compile(r"location|city", re.I))
                    location = location_el.get_text(strip=True) if location_el else "Philippines"

                    jobs.append({
                        "title": title,
                        "company": company,
                        "link": link,
                        "category": detect_category(title),
                        "location": location,
                        "source": "JobStreet PH",
                    })

            except Exception as e:
                logger.error(f"JobStreet error for '{keyword}': {e}")

        return jobs

    # ── ONLINEJOBS.PH ──────────────────────────────
    def scrape_onlinejobs_rss(self) -> List[Dict]:
        """OnlineJobs.ph - best source for VA & remote PH jobs"""
        from bs4 import BeautifulSoup
        jobs = []

        search_terms = [
            "virtual+assistant",
            "data+entry",
            "customer+service",
            "social+media",
            "admin",
        ]

        for term in search_terms:
            try:
                url = f"https://www.onlinejobs.ph/jobseekers/joblist?keyword={term}&jobtype=1"
                resp = requests.get(url, headers=HEADERS, timeout=15)
                soup = BeautifulSoup(resp.text, "html.parser")

                job_items = soup.find_all("div", class_=re.compile(r"job-post|jobpost", re.I))
                if not job_items:
                    job_items = soup.find_all("div", class_="row jobpost-row")

                for item in job_items[:10]:
                    title_el = item.find(["h2", "h3", "a"])
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)

                    link_el = item.find("a", href=True)
                    link = link_el["href"] if link_el else ""
                    if link and not link.startswith("http"):
                        link = "https://www.onlinejobs.ph" + link

                    company_el = item.find(class_=re.compile(r"company|employer", re.I))
                    company = company_el.get_text(strip=True) if company_el else "Unknown Employer"

                    jobs.append({
                        "title": title,
                        "company": company,
                        "link": link,
                        "category": detect_category(title),
                        "location": "Philippines (Remote)",
                        "source": "OnlineJobs.ph",
                    })

            except Exception as e:
                logger.error(f"OnlineJobs error for '{term}': {e}")

        return jobs

    # ── JOBSPH (Kalibrr) ──────────────────────────
    def scrape_jobsph_api(self) -> List[Dict]:
        """Kalibrr / Jobs.ph public job listings"""
        from bs4 import BeautifulSoup
        jobs = []

        keywords = ["call center", "virtual assistant", "BPO", "remote work", "POGO"]

        for keyword in keywords:
            try:
                url = f"https://www.kalibrr.com/job-board/te/philippines/l/philippines?q={keyword.replace(' ', '+')}"
                resp = requests.get(url, headers=HEADERS, timeout=15)
                soup = BeautifulSoup(resp.text, "html.parser")

                job_cards = soup.find_all("div", class_=re.compile(r"job-card|k-flex", re.I))
                if not job_cards:
                    # Try JSON-LD structured data
                    scripts = soup.find_all("script", type="application/ld+json")
                    for script in scripts:
                        try:
                            import json
                            data = json.loads(script.string or "{}")
                            if isinstance(data, dict) and data.get("@type") == "JobPosting":
                                title = data.get("title", "")
                                if is_relevant_job(title):
                                    jobs.append({
                                        "title": title,
                                        "company": data.get("hiringOrganization", {}).get("name", "Unknown"),
                                        "link": data.get("url", ""),
                                        "category": detect_category(title),
                                        "location": "Philippines",
                                        "source": "Kalibrr",
                                    })
                        except Exception:
                            pass
                    continue

                for card in job_cards[:8]:
                    title_el = card.find(["h2", "h3", "a"])
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    if not is_relevant_job(title):
                        continue

                    link_el = card.find("a", href=True)
                    link = link_el["href"] if link_el else ""
                    if link and not link.startswith("http"):
                        link = "https://www.kalibrr.com" + link

                    company_el = card.find(class_=re.compile(r"company|employer", re.I))
                    company = company_el.get_text(strip=True) if company_el else "Unknown"

                    jobs.append({
                        "title": title,
                        "company": company,
                        "link": link,
                        "category": detect_category(title),
                        "location": "Philippines",
                        "source": "Kalibrr",
                    })

            except Exception as e:
                logger.error(f"Kalibrr error for '{keyword}': {e}")

        return jobs
