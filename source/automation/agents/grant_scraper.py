"""Grant scraper agent - discovers grants from multiple public sources."""
import os
import re
import sys
from typing import Callable, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
from config import settings


SCRAPE_TARGETS = [
    {
        "key": "grants_gov",
        "search_url": "https://www.grants.gov/search-grants.html?keyword={query}",
        "item_selector": ".grant-item, .opportunity-card, .search-result",
        "title_selector": "h3 a, .grant-title",
        "link_selector": "h3 a",
        "description_selector": ".description, .summary, p",
        "deadline_selector": ".deadline, .close-date",
        "agency_selector": ".agency, .organization",
        "amount_selector": ".amount, .award-ceiling",
    },
]


API_TARGETS = [
    {
        "key": "grants_gov_api",
        "url": "https://api.grants.gov/v1/api/search2",
        "method": "post",
    },
    {
        "key": "federal_register_api",
        "url": "https://www.federalregister.gov/api/v1/documents.json",
    },
    {
        "key": "grants_gov_rss",
        "url": "https://www.grants.gov/rss/GG_NewOpp.xml",
    },
]


CATEGORY_RULES = {
    "Education": ["education", "literacy", "student", "school", "stem", "youth"],
    "Community": ["community", "family", "housing", "health", "public"],
    "Workforce": ["job", "employment", "training", "apprentice", "career"],
    "Arts & Culture": ["arts", "culture", "humanities", "heritage"],
}


def _query_tokens(query: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", (query or "").lower())}


def _matches_query(query: str, *parts: Optional[str]) -> bool:
    tokens = _query_tokens(query)
    if not tokens:
        return True
    haystack = " ".join(filter(None, parts)).lower()
    hits = sum(1 for token in tokens if token in haystack)
    return hits >= 1


def _infer_category(*parts: Optional[str]) -> str:
    blob = " ".join(filter(None, parts)).lower()
    for category, markers in CATEGORY_RULES.items():
        if any(marker in blob for marker in markers):
            return category
    return "General"


def _dedupe_results(items: list[dict]) -> list[dict]:
    deduped = []
    seen = set()
    for item in items:
        key = (
            (item.get("title") or "").strip().lower(),
            (item.get("source_url") or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


class GrantScraperAgent:
    def __init__(self):
        self.headless = settings.PLAYWRIGHT_HEADLESS
        self.timeout = settings.AUTOMATION_TIMEOUT_MS

    async def scrape(
        self,
        query: str,
        max_results: int = 50,
        progress_cb: Optional[Callable] = None,
    ) -> list[dict]:
        """Scrape grants from configured sources. Returns list of raw grant dicts."""
        # Prefer the public APIs; avoid a browser process when structured sources work.
        results = await self._scrape_via_http(query, max_results, progress_cb)
        if results:
            if progress_cb:
                await progress_cb(100, f"Found {len(results)} sourced opportunities")
            return _dedupe_results(results)[:max_results]
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self.headless)

                for i, target in enumerate(SCRAPE_TARGETS):
                    try:
                        if progress_cb:
                            pct = int((i / len(SCRAPE_TARGETS)) * 80)
                            await progress_cb(pct, f"Scraping {target['key']}")

                        page = await browser.new_page()
                        url = target["search_url"].format(query=query.replace(" ", "+"))
                        await page.goto(url, timeout=self.timeout)
                        await page.wait_for_load_state("networkidle", timeout=min(self.timeout, 15000))

                        items = await page.query_selector_all(target["item_selector"])
                        for item in items[: max_results * 2]:
                            grant = await self._extract_grant(item, target, url, query)
                            if grant:
                                results.append(grant)
                        await page.close()

                    except Exception as exc:
                        if progress_cb:
                            await progress_cb(None, f"Error scraping {target['key']}: {exc}")

                await browser.close()
        except Exception as exc:
            if progress_cb:
                await progress_cb(None, f"Browser scrape unavailable, falling back to HTTP parsing: {exc}")
            results.extend(await self._scrape_via_http(query, max_results, progress_cb))

        if not results:
            if progress_cb:
                await progress_cb(None, "Browser scrape returned no results, using HTTP/API fallback")
            results.extend(await self._scrape_via_http(query, max_results, progress_cb))

        results = _dedupe_results(results)[:max_results]

        if progress_cb:
            await progress_cb(100, f"Scraped {len(results)} grants")

        return results

    async def _scrape_via_http(
        self,
        query: str,
        max_results: int,
        progress_cb: Optional[Callable] = None,
    ) -> list[dict]:
        import httpx
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin

        results = []
        source_count = len(API_TARGETS) + len(SCRAPE_TARGETS)

        async with httpx.AsyncClient(follow_redirects=True, timeout=min(self.timeout / 1000, 20)) as client:
            for i, target in enumerate(API_TARGETS):
                try:
                    if progress_cb:
                        pct = int((i / source_count) * 80)
                        await progress_cb(pct, f"Fetching {target['key']}")

                    if target["key"] == "grants_gov_api":
                        response = await client.post(
                            target["url"],
                            json={
                                "keyword": query,
                                "oppStatuses": "posted",
                                "rows": max(25, max_results),
                                "startRecordNum": 0,
                            },
                            headers={
                                "User-Agent": "Mozilla/5.0",
                                "Content-Type": "application/json",
                            },
                            timeout=20,
                        )
                        response.raise_for_status()
                        if response.status_code == 200:
                            payload = response.json()
                            if payload.get('errorcode', 0) != 0:
                                raise RuntimeError('Grants.gov reported a search error')
                            # Handle both response shapes the API may return
                            opp_hits = (
                                payload.get("data", {}).get("oppHits")
                                or payload.get("oppHits")
                                or payload.get("opportunities")
                                or payload.get("hits")
                                or []
                            )
                            for opp in opp_hits:
                                title = opp.get("title") or opp.get("opportunityTitle", "")
                                if not title:
                                    continue
                                opp_id = opp.get("id") or opp.get("opportunityId", "")
                                opp_number = opp.get("number") or opp.get("opportunityNumber", "")
                                agency = opp.get("agencyName") or opp.get("agencyCode", "")
                                close_date = opp.get("closeDate") or opp.get("closingDate", "")
                                award_ceiling = opp.get("awardCeiling") or opp.get("awardCeilingFormatted")
                                synopsis = opp.get("synopsis", "")
                                cfda_list = opp.get("cfdaList") or opp.get("cfdaNumbers") or []
                                opp_url = (
                                    opp.get("oppUrl")
                                    or (f"https://www.grants.gov/search-results-detail/{opp_id}" if opp_id else None)
                                )

                                if not _matches_query(query, title, synopsis, agency):
                                    continue

                                amount = None
                                if award_ceiling:
                                    try:
                                        amount = float(str(award_ceiling).replace(",", "").replace("$", ""))
                                    except (ValueError, TypeError):
                                        amount = None

                                results.append({
                                    "source": "grants_gov_api",
                                    "title": title,
                                    "source_url": opp_url,
                                    "deadline_str": close_date,
                                    "funding_agency": agency or "Grants.gov",
                                    "amount": amount,
                                    "category": _infer_category(title, synopsis, agency),
                                    "description": synopsis[:500] if synopsis else None,
                                    "eligibility": None,
                                    "opportunity_number": opp_number,
                                    "cfda_numbers": cfda_list,
                                    "opportunity_id": str(opp_id) if opp_id else None,
                                })

                    elif target["key"] == "federal_register_api":
                        response = await client.get(
                            target["url"],
                            params={
                                "conditions[term]": query,
                                "conditions[type][]": "NOTICE",
                                "order": "newest",
                                "per_page": max(15, max_results),
                            },
                            headers={"User-Agent": "Mozilla/5.0"},
                        )
                        response.raise_for_status()
                        payload = response.json() if response.content else {}
                        for record in payload.get("results", []):
                            title = record.get("title")
                            summary = record.get("abstract") or record.get("type")
                            agency_names = ", ".join(
                                [a.get("name") for a in (record.get("agencies") or []) if a.get("name")]
                            )
                            if not title or not _matches_query(query, title, summary, agency_names):
                                continue
                            if not re.search(r'\b(grants?|funding|awards?|cooperative agreement)\b', f'{title} {summary}', re.I):
                                continue  # General regulatory/collection notices are not funding opportunities.

                            results.append(
                                {
                                    "source": "federal_register_api",
                                    "title": title,
                                    "source_url": record.get("html_url") or record.get("pdf_url"),
                                    "deadline_str": None,
                                    "published_at": record.get("publication_date"),
                                    "funding_agency": agency_names or "Federal Register",
                                    "amount": None,
                                    "category": _infer_category(title, summary, agency_names),
                                    "description": summary,
                                    "eligibility": None,
                                }
                            )

                    if target["key"] == "grants_gov_rss":
                        response = await client.get(target["url"], headers={"User-Agent": "Mozilla/5.0"})
                        response.raise_for_status()
                        soup_xml = BeautifulSoup(response.text, "xml")
                        entries = soup_xml.find_all("item")
                        for entry in entries:
                            title = (entry.find("title").get_text(strip=True) if entry.find("title") else "")
                            description = (entry.find("description").get_text(" ", strip=True) if entry.find("description") else "")
                            if not title or not _matches_query(query, title, description):
                                continue

                            results.append(
                                {
                                    "source": "grants_gov_rss",
                                    "title": title,
                                    "source_url": (entry.find("link").get_text(strip=True) if entry.find("link") else "") or None,
                                    "deadline_str": None,
                                    "published_at": (entry.find("pubDate").get_text(strip=True) if entry.find("pubDate") else "") or None,
                                    "funding_agency": "Grants.gov",
                                    "amount": None,
                                    "category": _infer_category(title, description),
                                    "description": description,
                                    "eligibility": None,
                                }
                            )

                except Exception as exc:
                    if progress_cb:
                        await progress_cb(None, f"API/feed error for {target['key']}: {exc}")

            if results:
                return _dedupe_results(results)[:max_results]

            for i, target in enumerate(SCRAPE_TARGETS):
                try:
                    if progress_cb:
                        pct = int(((len(API_TARGETS) + i) / source_count) * 80)
                        await progress_cb(pct, f"Fetching {target['key']} over HTTP")

                    url = target["search_url"].format(query=query.replace(" ", "+"))
                    response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, "html.parser")
                    items = soup.select(target["item_selector"])[: max_results * 2]

                    for item in items:
                        title_el = item.select_one(target["title_selector"])
                        if not title_el:
                            continue
                        title = title_el.get_text(" ", strip=True)
                        if not title:
                            continue

                        description_el = (
                            item.select_one(target["description_selector"])
                            if target.get("description_selector")
                            else None
                        )
                        description = description_el.get_text(" ", strip=True) if description_el else None

                        link_el = item.select_one(target["link_selector"])
                        href = link_el.get("href") if link_el else None
                        if href:
                            href = urljoin(url, href)

                        deadline_el = item.select_one(target["deadline_selector"]) if target.get("deadline_selector") else None
                        agency_el = item.select_one(target["agency_selector"]) if target.get("agency_selector") else None
                        amount_el = item.select_one(target["amount_selector"]) if target.get("amount_selector") else None
                        agency_text = agency_el.get_text(" ", strip=True) if agency_el else None

                        if not _matches_query(query, title, description, agency_text):
                            continue

                        amount = None
                        amount_str = amount_el.get_text(" ", strip=True) if amount_el else None
                        if amount_str:
                            nums = re.findall(r"[\d,]+", amount_str.replace("$", ""))
                            if nums:
                                try:
                                    amount = float(nums[-1].replace(",", ""))
                                except ValueError:
                                    amount = None

                        results.append(
                            {
                                "source": target["key"],
                                "title": title,
                                "source_url": href,
                                "deadline_str": deadline_el.get_text(" ", strip=True) if deadline_el else None,
                                "funding_agency": agency_text,
                                "amount": amount,
                                "category": _infer_category(title, description, agency_text),
                                "description": description,
                                "eligibility": None,
                            }
                        )
                except Exception as exc:
                    if progress_cb:
                        await progress_cb(None, f"HTTP scrape error for {target['key']}: {exc}")

        return _dedupe_results(results)[:max_results]

    async def _extract_grant(self, item, target: dict, base_url: str, query: str) -> Optional[dict]:
        try:
            title_el = await item.query_selector(target["title_selector"])
            title = (await title_el.inner_text()).strip() if title_el else None
            if not title:
                return None

            link_el = await item.query_selector(target["link_selector"])
            href = await link_el.get_attribute("href") if link_el else None
            if href and href.startswith("/"):
                from urllib.parse import urljoin

                href = urljoin(base_url, href)

            description = None
            if target.get("description_selector"):
                desc_el = await item.query_selector(target["description_selector"])
                if desc_el:
                    description = (await desc_el.inner_text()).strip()

            deadline = None
            if target.get("deadline_selector"):
                d_el = await item.query_selector(target["deadline_selector"])
                if d_el:
                    deadline = (await d_el.inner_text()).strip()

            agency = None
            if target.get("agency_selector"):
                a_el = await item.query_selector(target["agency_selector"])
                if a_el:
                    agency = (await a_el.inner_text()).strip()

            if not _matches_query(query, title, description, agency):
                return None

            amount_str = None
            if target.get("amount_selector"):
                amt_el = await item.query_selector(target["amount_selector"])
                if amt_el:
                    amount_str = (await amt_el.inner_text()).strip()

            amount = None
            if amount_str:
                nums = re.findall(r"[\d,]+", amount_str.replace("$", ""))
                if nums:
                    try:
                        amount = float(nums[-1].replace(",", ""))
                    except ValueError:
                        amount = None

            return {
                "source": target["key"],
                "title": title,
                "source_url": href,
                "deadline_str": deadline,
                "funding_agency": agency,
                "amount": amount,
                "category": _infer_category(title, description, agency),
                "description": description,
                "eligibility": None,
            }
        except Exception:
            return None
