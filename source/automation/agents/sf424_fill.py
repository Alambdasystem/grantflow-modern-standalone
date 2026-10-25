"""
SF-424 auto-fill agent.

Navigates to a grants.gov Workspace application using the saved OpenClaw profile,
locates the SF-424 form, and fills it with organization + application data.

SF-424 field mapping (grants.gov Workspace 2.0 / Workspace+):
  The Workspace renders SF-424 as an HTML form with JSF IDs. Since field IDs can vary
  across opportunity packages, we use a multi-selector approach: try the most specific
  ID first, then fall back to label-text matching and common name attributes.
"""
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

# SF-424 field selectors — ordered by specificity.
# Each entry is a list of CSS selectors tried in order until one matches.
SF424_FIELD_MAP = {
    "org_name": [
        "[id$='applicantName']",
        "[name*='applicantName']",
        "input[placeholder*='Legal Name']",
        "[id*='legalName']",
        "[id*='organizationName']",
    ],
    "ein": [
        "[id$='employerTaxpayerIdentificationNumber']",
        "[name*='ein']",
        "[name*='EIN']",
        "input[placeholder*='EIN']",
        "input[placeholder*='Employer']",
        "[id*='taxpayerId']",
    ],
    "uei": [
        "[id$='UEI']",
        "[id$='uei']",
        "[name*='UEI']",
        "[name*='uei']",
        "input[placeholder*='UEI']",
        "[id*='uniqueEntityId']",
        "[id*='duns']",
        "[name*='duns']",
    ],
    "address_street": [
        "[id$='streetAddress1']",
        "[name*='street1']",
        "input[placeholder*='Street']",
        "[id*='streetAddress']",
        "[id*='address1']",
    ],
    "address_city": [
        "[id$='city']",
        "[name*='city']",
        "input[placeholder*='City']",
    ],
    "address_state": [
        "select[id$='state']",
        "select[name*='state']",
        "[id*='stateCode']",
    ],
    "address_zip": [
        "[id$='zipCode']",
        "[name*='zip']",
        "input[placeholder*='ZIP']",
        "input[placeholder*='Zip']",
        "[id*='postalCode']",
    ],
    "address_country": [
        "select[id$='country']",
        "select[name*='country']",
        "[id*='countryCode']",
    ],
    "congressional_district": [
        "[id$='congressionalDistrict']",
        "[name*='congressionalDistrict']",
        "input[placeholder*='Congressional']",
    ],
    "project_title": [
        "[id$='projectTitle']",
        "[name*='projectTitle']",
        "input[placeholder*='Project Title']",
        "[id*='descriptiveTitle']",
    ],
    "project_description": [
        "textarea[id$='projectDescription']",
        "textarea[name*='projectDescription']",
        "textarea[placeholder*='Project Description']",
        "textarea[id*='abstract']",
    ],
    "amount_requested": [
        "[id$='federalFundsRequested']",
        "[name*='federalFunds']",
        "input[placeholder*='Federal Funds']",
        "[id*='amountRequested']",
        "[id*='fundsRequested']",
    ],
    "cfda_number": [
        "[id$='cfda']",
        "[id$='CFDA']",
        "[name*='cfda']",
        "input[placeholder*='CFDA']",
    ],
    "aor_first_name": [
        "[id$='aorFirstName']",
        "[id$='firstName']",
        "[name*='firstName']",
        "input[placeholder*='First Name']",
    ],
    "aor_last_name": [
        "[id$='aorLastName']",
        "[id$='lastName']",
        "[name*='lastName']",
        "input[placeholder*='Last Name']",
    ],
    "aor_title": [
        "[id$='aorTitle']",
        "[id$='title']",
        "[name*='title']",
        "input[placeholder*='Title']",
    ],
    "aor_phone": [
        "[id$='aorPhone']",
        "[id$='phone']",
        "[name*='phone']",
        "input[placeholder*='Phone']",
    ],
    "aor_email": [
        "[id$='aorEmail']",
        "[id$='email']",
        "[name*='email']",
        "input[placeholder*='Email']",
    ],
}


class SF424FillAgent:
    def __init__(self):
        self.timeout = 15000

    async def fill(
        self,
        workspace_url: str,
        org: dict,
        application: dict,
        progress_cb: Optional[Callable] = None,
    ) -> dict:
        """
        Navigate to a grants.gov Workspace application and fill the SF-424 form.

        Args:
            workspace_url: URL of the application in grants.gov Workspace
            org: dict with org profile fields (name, ein, uei, address, city, state, ...)
            application: dict with application fields (title, amount_requested, ...)
            progress_cb: async callable(pct, message)

        Returns:
            {
              "success": bool,
              "filled_fields": [list of field names filled],
              "skipped_fields": [list of field names not found],
              "screenshot": path,
              "error": str | None,
            }
        """
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout

        if not os.path.isdir(_OPENCLAW_PROFILE):
            return {
                "success": False,
                "error": "OpenClaw profile not found — connect to grants.gov first.",
                "filled_fields": [],
                "skipped_fields": [],
            }

        # Build the data dict mapping field keys to values
        data = {
            "org_name":              org.get("name", ""),
            "ein":                   org.get("ein", ""),
            "uei":                   org.get("uei", ""),
            "address_street":        org.get("address", ""),
            "address_city":          org.get("city", ""),
            "address_state":         org.get("state", ""),
            "address_zip":           org.get("zip_code", ""),
            "address_country":       org.get("country", "US"),
            "congressional_district": org.get("congressional_district", ""),
            "project_title":         application.get("title", ""),
            "project_description":   application.get("proposal_text", "")[:500] if application.get("proposal_text") else "",
            "amount_requested":      str(int(application["amount_requested"])) if application.get("amount_requested") else "",
            "cfda_number":           application.get("cfda_number", ""),
            "aor_first_name":        org.get("aor_first_name", ""),
            "aor_last_name":         org.get("aor_last_name", ""),
            "aor_title":             org.get("aor_title", ""),
            "aor_phone":             org.get("aor_phone", ""),
            "aor_email":             org.get("aor_email", ""),
        }

        # Remove empty fields so we don't overwrite existing values with blanks
        data = {k: v for k, v in data.items() if v}

        filled = []
        skipped = []
        screenshot_path = None

        async with async_playwright() as pw:
            context = None
            page = None
            try:
                try:
                    context = await pw.chromium.launch_persistent_context(
                        user_data_dir=_OPENCLAW_PROFILE,
                        headless=False,  # Visible so user can see progress and intervene
                        channel="chrome",
                        args=["--disable-blink-features=AutomationControlled"],
                        ignore_https_errors=True,
                    )
                except Exception:
                    context = await pw.chromium.launch_persistent_context(
                        user_data_dir=_OPENCLAW_PROFILE,
                        headless=False,
                        ignore_https_errors=True,
                    )

                await context.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
                )
                page = await context.new_page()

                if progress_cb:
                    await progress_cb(10, "Opening Grants.gov Workspace application")

                await page.goto(workspace_url, timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=20000)
                await asyncio.sleep(2)

                # Check session is still valid
                cur = page.url
                if "secure.login.gov" in cur or ("login" in cur.lower() and "grants.gov" not in cur):
                    return {
                        "success": False,
                        "error": "Session expired — reconnect to grants.gov from the Providers page.",
                        "filled_fields": [],
                        "skipped_fields": [],
                        "requires_reconnect": True,
                    }

                # Look for SF-424 link/tab within the application
                sf424_link = await page.query_selector(
                    "a[href*='SF424'], a[title*='SF-424'], a[id*='sf424'], "
                    "td:has-text('SF-424'), span:has-text('SF 424')"
                )
                if sf424_link:
                    if progress_cb:
                        await progress_cb(20, "Opening SF-424 form")
                    await sf424_link.click()
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    await asyncio.sleep(2)

                if progress_cb:
                    await progress_cb(30, f"Filling {len(data)} SF-424 fields")

                # Fill each field
                total = len(data)
                for idx, (field_key, value) in enumerate(data.items()):
                    if not value:
                        continue

                    selectors = SF424_FIELD_MAP.get(field_key, [])
                    filled_this = False

                    for selector in selectors:
                        try:
                            el = await page.query_selector(selector)
                            if not el:
                                continue
                            tag = await el.evaluate("el => el.tagName.toLowerCase()")
                            if tag == "select":
                                await el.select_option(label=value, timeout=3000)
                            else:
                                await el.fill(value, timeout=3000)
                            filled.append(field_key)
                            filled_this = True
                            break
                        except Exception:
                            continue

                    if not filled_this:
                        skipped.append(field_key)

                    if progress_cb and idx % 3 == 0:
                        pct = 30 + int((idx / total) * 50)
                        await progress_cb(pct, f"Filling SF-424… ({idx + 1}/{total})")

                # Save the form
                if progress_cb:
                    await progress_cb(85, "Saving SF-424 form")

                save_btn = await page.query_selector(
                    "input[value='Save'][type='submit'], "
                    "button:has-text('Save'), "
                    "input[id*='save']"
                )
                if save_btn:
                    await save_btn.click()
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    await asyncio.sleep(1.5)

                # Screenshot after fill
                scr_dir = os.path.join(
                    os.path.dirname(__file__), "..", "..", "backend", "automation_screenshots"
                )
                os.makedirs(scr_dir, exist_ok=True)
                screenshot_path = os.path.join(scr_dir, f"sf424_filled_{os.getpid()}.png")
                try:
                    await page.screenshot(path=screenshot_path, full_page=False)
                except Exception:
                    pass

                if progress_cb:
                    await progress_cb(100, f"SF-424 filled: {len(filled)} fields, {len(skipped)} skipped")

                return {
                    "success": len(filled) > 0,
                    "filled_fields": filled,
                    "skipped_fields": skipped,
                    "screenshot": screenshot_path,
                    "error": None if filled else "No SF-424 fields were found on this page.",
                }

            except Exception as exc:
                if page:
                    scr_dir = os.path.join(
                        os.path.dirname(__file__), "..", "..", "backend", "automation_screenshots"
                    )
                    os.makedirs(scr_dir, exist_ok=True)
                    screenshot_path = os.path.join(scr_dir, f"sf424_error_{os.getpid()}.png")
                    try:
                        await page.screenshot(path=screenshot_path)
                    except Exception:
                        pass
                return {
                    "success": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "filled_fields": filled,
                    "skipped_fields": skipped,
                    "screenshot": screenshot_path,
                }
            finally:
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass
