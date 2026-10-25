"""
Grant Requirements Discovery Agent.

Fetches the real submission requirements for a specific grant opportunity:
- What forms are required (SF-424, SF-424A, project narrative, etc.)
- What attachments are mandatory vs optional
- Page limits and formatting rules
- Eligibility requirements
- Application package instructions

Sources (in order):
  1. Grants.gov REST API  (/opportunity/details)
  2. Playwright navigation to the opportunity synopsis + apply page
     (only if opp_id or source_url provided and OpenClaw profile exists)
"""
import asyncio
import os
import sys
import re
from typing import Optional, Callable

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

_OPENCLAW_PROFILE = os.getenv('GFM_BROWSER_PROFILE_DIR') or os.path.normpath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "..",
        "openclaw_login_agent_data", "_trusted_chrome_profile",
    )
)

_GG_API_BASE = "https://apply07.grants.gov/grantsws/rest"
_GG_SEARCH_URL = f"{_GG_API_BASE}/opportunities/search/"
_GG_DETAIL_URL = f"{_GG_API_BASE}/opportunity/details"


class GrantRequirementsAgent:
    """Discovers what a specific grant actually requires for submission."""

    async def fetch(
        self,
        opp_id: Optional[str] = None,
        opp_number: Optional[str] = None,
        source_url: Optional[str] = None,
        grant_title: Optional[str] = None,
        progress_cb: Optional[Callable] = None,
    ) -> dict:
        """
        Fetch full submission requirements for a grant opportunity.

        Returns:
            {
              "success": bool,
              "opp_id": str,
              "opp_number": str,
              "title": str,
              "synopsis": str,
              "agency": str,
              "cfda_numbers": list[str],
              "deadline": str,
              "award_ceiling": float | None,
              "award_floor": float | None,
              "eligibility": str,
              "eligible_applicants": list[str],
              "required_forms": list[{name, form_number, description, is_mandatory}],
              "required_attachments": list[{name, description, page_limit, is_mandatory}],
              "package_instructions": str,
              "application_url": str | None,
              "source": str,   # "api" | "api+browser" | "browser"
              "error": str | None,
            }
        """
        result = {
            "success": False,
            "opp_id": opp_id,
            "opp_number": opp_number,
            "title": grant_title or "",
            "synopsis": "",
            "agency": "",
            "cfda_numbers": [],
            "deadline": "",
            "award_ceiling": None,
            "award_floor": None,
            "eligibility": "",
            "eligible_applicants": [],
            "required_forms": [],
            "required_attachments": [],
            "package_instructions": "",
            "application_url": source_url,
            "source": "api",
            "error": None,
        }

        if progress_cb:
            await progress_cb(5, "Resolving opportunity ID from grants.gov API")

        # ── Step 1: resolve opp_id + grab search hit metadata ────────────────
        hit_data: Optional[dict] = None

        if not opp_id and opp_number:
            opp_id, hit_data = await self._search_opp(opp_number=opp_number)
            result["opp_id"] = opp_id

        if not opp_id and source_url:
            opp_id = self._extract_opp_id_from_url(source_url)
            result["opp_id"] = opp_id

        if not opp_id and grant_title:
            opp_id, hit_data = await self._search_opp(keyword=grant_title)
            result["opp_id"] = opp_id

        # Merge search hit metadata (title, agency, cfda, deadline, opp_number)
        if hit_data:
            self._merge_search_hit(result, hit_data)

        # ── Step 2: Playwright scrape for synopsis + package forms ────────────
        has_profile = os.path.isdir(_OPENCLAW_PROFILE)
        if has_profile and (opp_id or source_url):
            if progress_cb:
                await progress_cb(30, "Opening grants.gov opportunity page in browser")
            browser_data = await self._scrape_with_browser(
                opp_id=opp_id,
                source_url=source_url,
                opp_number=result.get("opp_number"),
                progress_cb=progress_cb,
            )
            if browser_data.get("success"):
                self._merge_browser_data(result, browser_data)
                result["source"] = "api+browser" if hit_data else "browser"
        elif not has_profile:
            result["error"] = "OpenClaw profile not found — connect to grants.gov first for full package details"

        result["success"] = bool(
            result["required_forms"] or result["synopsis"] or result["eligibility"]
            or result["agency"] or result["opp_number"]
        )
        return result

    # ── REST API helpers ──────────────────────────────────────────────────────

    async def _search_opp(
        self,
        opp_number: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[dict]]:
        """Search grants.gov for an opportunity. Returns (opp_id, hit_dict)."""
        body: dict = {"rows": 1, "startRecordNum": 0}
        if opp_number:
            body["oppNumber"] = opp_number
        elif keyword:
            body["keyword"] = keyword[:80]
        else:
            return None, None

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(_GG_SEARCH_URL, json=body)
                if r.status_code == 200:
                    data = r.json()
                    hits = data.get("oppHits") or []
                    if hits:
                        hit = hits[0]
                        opp_id = str(hit.get("id") or hit.get("oppId") or "")
                        return opp_id or None, hit
        except Exception:
            pass
        return None, None

    def _extract_opp_id_from_url(self, url: str) -> Optional[str]:
        patterns = [
            r"oppId=(\d+)",
            r"opportunity[_-]?id[=\/](\d+)",
            r"results-detail\/(\d+)",
            r"\/(\d{6,})(?:[\/\?#]|$)",
        ]
        for pat in patterns:
            m = re.search(pat, url, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    def _merge_search_hit(self, result: dict, hit: dict):
        """Merge data from a grants.gov search hit (flat structure) into result."""
        # Known fields from grants.gov search API:
        # id, number, title, agencyCode, agency, openDate, closeDate, oppStatus,
        # docType, cfdaList
        if not result["title"]:
            result["title"] = hit.get("title", "")
        if not result["agency"]:
            result["agency"] = hit.get("agency") or hit.get("agencyCode", "")
        if not result["opp_number"]:
            result["opp_number"] = hit.get("number") or hit.get("opportunityNumber", "")
        if not result["deadline"]:
            result["deadline"] = hit.get("closeDate") or hit.get("responseDate") or ""

        cfdas = hit.get("cfdaList") or hit.get("cfdaNumbers") or []
        if isinstance(cfdas, list) and not result["cfda_numbers"]:
            result["cfda_numbers"] = [str(c) for c in cfdas if c]

    def _merge_api_data(self, result: dict, data: dict):
        """Pull fields from grants.gov REST API detail response into result (legacy)."""
        opp = data.get("opportunity") or data.get("opportunityDetails") or data

        result["title"] = result["title"] or opp.get("title") or opp.get("opportunityTitle", "")
        result["agency"] = result["agency"] or opp.get("agencyName") or opp.get("agency") or opp.get("agencyCode", "")
        result["opp_number"] = result["opp_number"] or opp.get("number") or opp.get("opportunityNumber", "")

        synopsis_obj = opp.get("synopsis") or {}
        if isinstance(synopsis_obj, dict):
            result["synopsis"] = result["synopsis"] or (
                synopsis_obj.get("synopsisDesc")
                or synopsis_obj.get("programDescription")
                or synopsis_obj.get("description", "")
            )
            result["eligibility"] = result["eligibility"] or synopsis_obj.get("applicantEligibilityDesc", "")
            result["deadline"] = result["deadline"] or synopsis_obj.get("responseDate") or synopsis_obj.get("archiveDate", "")
            if result["award_ceiling"] is None:
                result["award_ceiling"] = synopsis_obj.get("awardCeiling")
            if result["award_floor"] is None:
                result["award_floor"] = synopsis_obj.get("awardFloor")
            elig_types = synopsis_obj.get("applicantTypes") or []
            if isinstance(elig_types, list) and not result["eligible_applicants"]:
                result["eligible_applicants"] = [str(t) for t in elig_types if t]
        elif isinstance(synopsis_obj, str):
            result["synopsis"] = result["synopsis"] or synopsis_obj

        cfdas = opp.get("cfdaList") or opp.get("cfdaNumbers") or []
        if isinstance(cfdas, list):
            result["cfda_numbers"] = [str(c) for c in cfdas if c]

        # Package / forms from API
        packages = opp.get("opportunityPackages") or opp.get("packages") or []
        for pkg in (packages if isinstance(packages, list) else []):
            forms = pkg.get("forms") or pkg.get("packageForms") or []
            for form in (forms if isinstance(forms, list) else []):
                result["required_forms"].append({
                    "name": form.get("formName") or form.get("name", ""),
                    "form_number": form.get("formNumber") or form.get("number", ""),
                    "description": form.get("description", ""),
                    "is_mandatory": form.get("mandatory", True),
                })

        # Application URL
        if not result["application_url"]:
            result["application_url"] = opp.get("synopsisUrl") or opp.get("applicationUrl") or ""

    # ── Browser scrape helpers ────────────────────────────────────────────────

    async def _scrape_with_browser(
        self,
        opp_id: Optional[str],
        source_url: Optional[str],
        opp_number: Optional[str],
        progress_cb: Optional[Callable],
    ) -> dict:
        from playwright.async_api import async_playwright

        browser_result = {
            "success": False,
            "required_forms": [],
            "required_attachments": [],
            "package_instructions": "",
            "synopsis": "",
            "eligibility": "",
            "application_url": "",
        }

        # Build the URL to navigate to
        if opp_id:
            target_url = f"https://www.grants.gov/search-results-detail/{opp_id}"
        elif source_url and "grants.gov" in source_url:
            target_url = source_url
        else:
            return browser_result

        async with async_playwright() as pw:
            context = None
            try:
                try:
                    context = await pw.chromium.launch_persistent_context(
                        user_data_dir=_OPENCLAW_PROFILE,
                        headless=True,
                        channel="chrome",
                        args=["--disable-blink-features=AutomationControlled"],
                        ignore_https_errors=True,
                    )
                except Exception:
                    context = await pw.chromium.launch_persistent_context(
                        user_data_dir=_OPENCLAW_PROFILE,
                        headless=True,
                        ignore_https_errors=True,
                    )

                await context.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
                )
                page = await context.new_page()

                # Navigate to opportunity synopsis page — grants.gov is Angular SPA,
                # so we wait for the content div to appear rather than just dom-ready
                await page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
                try:
                    await page.wait_for_selector("main, [class*='synopsis'], [class*='opportunity'], app-synopsis", timeout=8000)
                except Exception:
                    pass
                await asyncio.sleep(2)

                if progress_cb:
                    await progress_cb(55, "Reading synopsis and eligibility from grants.gov")

                # ── Full page text extraction (grants.gov Angular SPA) ────────
                # Exclude nav/footer/sidebar elements and grab main content area only.
                full_page_text = ""
                try:
                    # Remove nav and footer before grabbing text
                    await page.evaluate("""
                        () => {
                            const sel = 'nav, footer, header, [class*="footer"], [class*="header"], [class*="nav"], [role="navigation"], [role="banner"], [role="contentinfo"]';
                            document.querySelectorAll(sel).forEach(el => el.remove());
                        }
                    """)
                    main_el = await page.query_selector("main, #main-content, [role='main'], app-root, body")
                    if main_el:
                        full_page_text = (await main_el.text_content() or "").strip()
                except Exception:
                    pass

                # ── Synopsis — try specific selectors first, fall back to text parse ──
                synopsis_sel = [
                    "app-synopsis p", "[class*='synopsis'] p", "[class*='synopsis-desc']",
                    ".synopsis-description", ".opportunity-synopsis", "#synopsis-description",
                    ".program-description p", "[data-testid*='synopsis']",
                    "section.description p", "[class*='description'] p",
                ]
                for sel in synopsis_sel:
                    els = await page.query_selector_all(sel)
                    texts = []
                    for el in els[:5]:
                        t = (await el.text_content() or "").strip()
                        if t:
                            texts.append(t)
                    combined = " ".join(texts)
                    if len(combined) > 80:
                        browser_result["synopsis"] = combined[:3000]
                        break

                # ── Eligibility ───────────────────────────────────────────────
                elig_sel = [
                    "app-eligibility p", "[class*='eligibility'] p",
                    ".eligibility-description", "#eligible-applicants",
                    "[class*='eligible'] p", ".applicant-eligibility p",
                ]
                for sel in elig_sel:
                    els = await page.query_selector_all(sel)
                    texts = []
                    for el in els[:5]:
                        t = (await el.text_content() or "").strip()
                        if t:
                            texts.append(t)
                    combined = " ".join(texts)
                    if len(combined) > 20:
                        browser_result["eligibility"] = combined[:2000]
                        break

                # Fall back to parsing full page text for synopsis/eligibility
                if not browser_result["synopsis"] and full_page_text:
                    browser_result["synopsis"] = self._extract_section(full_page_text, ["synopsis", "description", "program description"], 3000)
                if not browser_result["eligibility"] and full_page_text:
                    browser_result["eligibility"] = self._extract_section(full_page_text, ["eligibility", "eligible applicants", "who can apply"], 2000)

                if progress_cb:
                    await progress_cb(65, "Looking for application package link")

                # ── Find the "Apply / View Package" link ─────────────────────
                package_url = None
                apply_link_sels = [
                    "a[href*='workspace']", "a[href*='apply']",
                    "a[href*='package']", "a:has-text('Apply Now')",
                    "a:has-text('View Package')", "a:has-text('Application Package')",
                    "button:has-text('Apply')",
                ]
                for sel in apply_link_sels:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            href = await el.get_attribute("href") or ""
                            if href and "register" not in href.lower():
                                if href.startswith("http"):
                                    package_url = href
                                elif href.startswith("/"):
                                    package_url = f"https://www.grants.gov{href}"
                                if package_url:
                                    break
                    except Exception:
                        continue

                # Try the apply07 instructions page directly
                if not package_url and opp_id:
                    package_url = f"https://apply07.grants.gov/apply/opportunities/instructions/oppInstructions.jftl?mode=SYNOPS&oppId={opp_id}"

                if package_url:
                    if progress_cb:
                        await progress_cb(72, "Navigating to application package instructions")
                    try:
                        await page.goto(package_url, timeout=25000, wait_until="domcontentloaded")
                        await asyncio.sleep(2)

                        # ── Package forms table ───────────────────────────────
                        await self._scrape_forms_table(page, browser_result)

                        # ── Package instructions ──────────────────────────────
                        instr_sel = [
                            ".package-instructions", ".instructions-text",
                            "#packageInstructions", "textarea[id*='instructions']",
                            ".opportunity-instructions", "pre.instructions",
                            "div.instructions p",
                        ]
                        for sel in instr_sel:
                            el = await page.query_selector(sel)
                            if el:
                                txt = (await el.text_content() or "").strip()
                                if len(txt) > 50:
                                    browser_result["package_instructions"] = txt[:5000]
                                    break

                        browser_result["application_url"] = page.url
                    except Exception:
                        browser_result["application_url"] = target_url

                # If we still have no forms, try scraping the current page forms section
                if not browser_result["required_forms"]:
                    await self._scrape_forms_table(page, browser_result)

                # Parse package requirements from full page text as last resort
                if not browser_result["required_forms"] and full_page_text:
                    self._parse_forms_from_text(full_page_text, browser_result)

                browser_result["success"] = bool(
                    browser_result["required_forms"]
                    or browser_result["synopsis"]
                    or browser_result["eligibility"]
                )

                if progress_cb:
                    await progress_cb(90, f"Found {len(browser_result['required_forms'])} required forms")

            except Exception as exc:
                browser_result["error"] = str(exc)
            finally:
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass

        return browser_result

    async def _scrape_forms_table(self, page, result: dict):
        """Extract required forms / attachments from grants.gov package tables."""
        # Try the forms table — grants.gov renders this as an HTML table
        form_rows = await page.query_selector_all(
            "table[id*='form'] tr, table[class*='form'] tr, "
            "table[class*='package'] tr, .form-list tr, "
            "#formTable tr, .mandatory-forms tr"
        )

        for row in form_rows:
            cells = await row.query_selector_all("td, th")
            if len(cells) < 2:
                continue
            texts = []
            for cell in cells:
                txt = (await cell.text_content() or "").strip()
                texts.append(txt)

            if not texts[0] or texts[0].lower() in ("form", "name", "title", "description"):
                continue

            form_name = texts[0]
            form_number = texts[1] if len(texts) > 1 else ""
            mandatory_text = " ".join(texts).lower()
            is_mandatory = "mandatory" in mandatory_text or "required" in mandatory_text or "m" == texts[-1].lower()
            description = texts[2] if len(texts) > 2 else ""

            # Classify as form vs attachment
            is_attachment = any(kw in form_name.lower() for kw in (
                "narrative", "attachment", "abstract", "budget justification",
                "resume", "cv", "letter", "certification", "assurance",
                "data management", "facilities", "equipment", "references",
            ))

            entry = {
                "name": form_name,
                "form_number": form_number,
                "description": description,
                "is_mandatory": is_mandatory,
            }

            if is_attachment:
                if "page_limit" not in entry:
                    page_match = re.search(r"(\d+)\s*page", mandatory_text)
                    entry["page_limit"] = int(page_match.group(1)) if page_match else None
                result["required_attachments"].append(entry)
            else:
                result["required_forms"].append(entry)

        # Also look for checklist items (grants.gov sometimes uses a checklist format)
        checklist_items = await page.query_selector_all(
            ".checklist-item, .required-document, .package-component, "
            "li[class*='form'], li[class*='required'], .submission-requirement"
        )
        for item in checklist_items:
            txt = (await item.text_content() or "").strip()
            if not txt or len(txt) < 5:
                continue
            is_mandatory = any(w in txt.lower() for w in ("mandatory", "required", "must"))
            is_optional = any(w in txt.lower() for w in ("optional", "if applicable", "as needed"))

            entry = {
                "name": txt[:200],
                "form_number": "",
                "description": "",
                "is_mandatory": is_mandatory or not is_optional,
            }

            is_attachment = any(kw in txt.lower() for kw in (
                "narrative", "attachment", "abstract", "budget justification",
                "resume", "letter", "certification", "assurance",
            ))

            if is_attachment:
                page_match = re.search(r"(\d+)\s*page", txt.lower())
                entry["page_limit"] = int(page_match.group(1)) if page_match else None
                result["required_attachments"].append(entry)
            elif "sf-" in txt.lower() or "sf424" in txt.lower().replace(" ", ""):
                result["required_forms"].append(entry)

        # Deduplicate by name
        seen = set()
        for key in ("required_forms", "required_attachments"):
            unique = []
            for item in result[key]:
                if item["name"] not in seen:
                    seen.add(item["name"])
                    unique.append(item)
            result[key] = unique

    def _merge_browser_data(self, result: dict, browser: dict):
        if browser.get("synopsis") and not result["synopsis"]:
            result["synopsis"] = browser["synopsis"]
        if browser.get("eligibility") and not result["eligibility"]:
            result["eligibility"] = browser["eligibility"]
        if browser.get("package_instructions"):
            result["package_instructions"] = browser["package_instructions"]
        if browser.get("application_url"):
            result["application_url"] = browser["application_url"]

        # Merge forms — add browser-found ones that API didn't return
        existing_names = {f["name"].lower() for f in result["required_forms"]}
        for form in browser.get("required_forms", []):
            if form["name"].lower() not in existing_names:
                result["required_forms"].append(form)
                existing_names.add(form["name"].lower())

        existing_att = {a["name"].lower() for a in result["required_attachments"]}
        for att in browser.get("required_attachments", []):
            if att["name"].lower() not in existing_att:
                result["required_attachments"].append(att)
                existing_att.add(att["name"].lower())

    def _extract_section(self, text: str, section_keywords: list, max_len: int) -> str:
        """Find a section in plain text by keyword and extract the following sentences."""
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if any(kw in line.lower() for kw in section_keywords):
                # Grab following lines until blank section
                snippet = []
                for l in lines[i + 1:i + 30]:
                    if len(" ".join(snippet)) > max_len:
                        break
                    stripped = l.strip()
                    if stripped:
                        snippet.append(stripped)
                result = " ".join(snippet).strip()
                if len(result) > 30:
                    return result[:max_len]
        return ""

    def _parse_forms_from_text(self, text: str, result: dict):
        """Parse common federal form names out of page text as last-resort fallback."""
        known_forms = [
            ("SF-424", "SF-424", "Application for Federal Assistance"),
            ("SF-424A", "SF-424A", "Budget Information — Non-Construction"),
            ("SF-424B", "SF-424B", "Assurances — Non-Construction"),
            ("SF-424C", "SF-424C", "Budget Information — Construction"),
            ("SF-424D", "SF-424D", "Assurances — Construction"),
            ("SF-LLL", "SF-LLL", "Lobbying Disclosure"),
            ("Project Narrative", "", "Narrative description of the proposed project"),
            ("Budget Justification", "", "Detailed budget justification narrative"),
            ("Abstract", "", "Project abstract or summary"),
            ("Logic Model", "", "Program logic model"),
            ("Evaluation Plan", "", "Evaluation and performance measurement plan"),
            ("Resume/CV", "", "Key personnel biographical sketches"),
        ]
        text_lower = text.lower()
        for name, form_number, description in known_forms:
            if name.lower() in text_lower:
                is_attachment = not form_number.startswith("SF-")
                entry = {
                    "name": name,
                    "form_number": form_number,
                    "description": description,
                    "is_mandatory": True,
                }
                if is_attachment:
                    page_match = re.search(rf"{re.escape(name.lower())}.*?(\d+)\s*page", text_lower)
                    entry["page_limit"] = int(page_match.group(1)) if page_match else None
                    existing = {a["name"].lower() for a in result["required_attachments"]}
                    if name.lower() not in existing:
                        result["required_attachments"].append(entry)
                else:
                    existing = {f["name"].lower() for f in result["required_forms"]}
                    if name.lower() not in existing:
                        result["required_forms"].append(entry)
