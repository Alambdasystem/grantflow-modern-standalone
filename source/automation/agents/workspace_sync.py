"""Workspace sync agent — reads grants.gov Workspace after login via saved OpenClaw profile."""
import asyncio
import os
import sys
from typing import Optional, Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

_OPENCLAW_PROFILE = os.getenv('GFM_BROWSER_PROFILE_DIR') or os.path.normpath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "..",
        "openclaw_login_agent_data", "_trusted_chrome_profile",
    )
)

WORKSPACE_URL = "https://apply07.grants.gov/apply/applicantEApply.faces"

# Map grants.gov status strings to GrantFlow application statuses
_STATUS_MAP = {
    "in progress": "draft",
    "work in progress": "draft",
    "submitted": "submitted",
    "submission received": "submitted",
    "validated": "submitted",
    "received by agency": "submitted",
    "awarded": "approved",
    "not funded": "rejected",
    "rejected": "rejected",
    "withdrawn": "rejected",
}


class WorkspaceSyncAgent:
    async def sync(self, progress_cb: Optional[Callable] = None) -> dict:
        """
        Navigate to the grants.gov Workspace using the saved OpenClaw profile and return all
        applications found in the workspace table.

        Returns:
          {
            "success": bool,
            "applications": [{"title", "opportunity_number", "cfda", "workspace_status",
                               "status", "last_modified", "workspace_url", "source"}, ...],
            "workspace_url": str,
            "error": str | None,
            "requires_reconnect": bool,
          }
        """
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout

        if not os.path.isdir(_OPENCLAW_PROFILE):
            return {
                "success": False,
                "error": "OpenClaw profile not found — connect to grants.gov first via the Providers page.",
                "applications": [],
                "requires_reconnect": True,
            }

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-first-run",
        ]

        async with async_playwright() as pw:
            context = None
            page = None
            try:
                try:
                    context = await pw.chromium.launch_persistent_context(
                        user_data_dir=_OPENCLAW_PROFILE,
                        headless=True,
                        channel="chrome",
                        args=launch_args,
                        ignore_https_errors=True,
                    )
                except Exception:
                    try:
                        context = await pw.chromium.launch_persistent_context(
                            user_data_dir=_OPENCLAW_PROFILE,
                            headless=True,
                            args=launch_args,
                            ignore_https_errors=True,
                        )
                    except Exception as launch_err:
                        return {
                            "success": False,
                            "error": f"Could not launch Chrome: {launch_err}",
                            "applications": [],
                        }

                await context.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
                )
                page = await context.new_page()

                if progress_cb:
                    await progress_cb(20, "Navigating to Grants.gov Workspace")

                await page.goto(WORKSPACE_URL, timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=20000)
                await asyncio.sleep(2)

                cur = page.url

                # Redirected to login → session expired
                if "secure.login.gov" in cur or ("login" in cur.lower() and "grants.gov" not in cur):
                    return {
                        "success": False,
                        "error": "Session expired — reconnect to grants.gov from the Providers page.",
                        "applications": [],
                        "requires_reconnect": True,
                    }

                if progress_cb:
                    await progress_cb(45, "Reading Workspace application list")

                # Wait a bit for any JS-driven table to render
                await asyncio.sleep(3)

                applications = await _extract_applications(page)

                if progress_cb:
                    await progress_cb(90, f"Found {len(applications)} applications in Workspace")

                return {
                    "success": True,
                    "applications": applications,
                    "workspace_url": page.url,
                    "error": None,
                    "requires_reconnect": False,
                }

            except Exception as exc:
                return {
                    "success": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "applications": [],
                }
            finally:
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass

    async def check_application_status(
        self,
        workspace_url: str,
        progress_cb: Optional[Callable] = None,
    ) -> dict:
        """
        Navigate directly to a specific workspace application page and read its current status.
        """
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout

        if not os.path.isdir(_OPENCLAW_PROFILE):
            return {"success": False, "error": "OpenClaw profile missing", "status": None}

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

                page = await context.new_page()

                if progress_cb:
                    await progress_cb(20, "Checking application status in Workspace")

                await page.goto(workspace_url, timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=20000)
                await asyncio.sleep(2)

                cur = page.url
                if "secure.login.gov" in cur or ("login" in cur.lower() and "grants.gov" not in cur):
                    return {
                        "success": False,
                        "error": "Session expired — reconnect to grants.gov.",
                        "status": None,
                        "requires_reconnect": True,
                    }

                page_text = (await page.evaluate("() => document.body.innerText")).lower()

                detected_status = None
                for status_raw, gf_status in _STATUS_MAP.items():
                    if status_raw in page_text:
                        detected_status = gf_status
                        break

                # Also look for the specific status display elements
                status_el = await page.query_selector(".applicationStatus, .app-status, [id*='status']")
                raw_status_text = None
                if status_el:
                    raw_status_text = (await status_el.inner_text()).strip()
                    if raw_status_text:
                        detected_status = _STATUS_MAP.get(raw_status_text.lower(), detected_status)

                return {
                    "success": True,
                    "status": detected_status,
                    "raw_status": raw_status_text,
                    "page_url": page.url,
                }

            except Exception as exc:
                return {"success": False, "error": f"{type(exc).__name__}: {exc}", "status": None}
            finally:
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass


async def _extract_applications(page) -> list[dict]:
    """Parse the workspace application table from the current page."""
    apps = []
    seen_titles = set()

    # grants.gov workspace uses JSF/RichFaces — multiple possible row selectors
    row_selectors = [
        "tr.rich-table-row",
        "tr[class*='rowClass']",
        "table.applicationList tbody tr",
        "table[id*='applicants'] tbody tr",
        "tbody tr",
    ]

    rows = []
    for sel in row_selectors:
        rows = await page.query_selector_all(sel)
        if rows:
            break

    for row in rows:
        try:
            cells = await row.query_selector_all("td")
            if len(cells) < 2:
                continue

            texts = [(await c.inner_text()).strip() for c in cells]

            # Skip header rows
            title = texts[0]
            if not title or title.lower() in ("application title", "title", "name", ""):
                continue
            if title in seen_titles:
                continue
            seen_titles.add(title)

            opp_number = texts[1] if len(texts) > 1 else ""
            cfda = texts[2] if len(texts) > 2 else ""
            status_raw = texts[3] if len(texts) > 3 else ""
            last_modified = texts[4] if len(texts) > 4 else ""

            gf_status = _STATUS_MAP.get(status_raw.lower().strip(), "draft")

            # Grab application link (first <a> in row)
            link_el = await row.query_selector("a[href]")
            href = None
            if link_el:
                href = await link_el.get_attribute("href")
                if href and not href.startswith("http"):
                    href = "https://apply07.grants.gov" + href

            apps.append({
                "title": title,
                "opportunity_number": opp_number,
                "cfda": cfda,
                "workspace_status": status_raw,
                "status": gf_status,
                "last_modified": last_modified,
                "workspace_url": href,
                "source": "grants_gov_workspace",
            })
        except Exception:
            continue

    return apps
