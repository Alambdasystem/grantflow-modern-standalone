"""Form filler agent — AI-guided portal form completion using Playwright."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
from config import settings


class FormFillerAgent:
    def __init__(self):
        self.headless = settings.PLAYWRIGHT_HEADLESS
        self.timeout = settings.AUTOMATION_TIMEOUT_MS

    async def autofill(
        self,
        portal_url: str,
        form_data: dict,
        storage_state: dict | None = None,
        progress_cb=None,
    ) -> dict:
        """
        Navigate to portal_url, restore session, and fill all form fields from form_data.
        Returns: {filled_count, screenshot, error}
        """
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
            context_kwargs = {}
            if storage_state:
                import tempfile, json
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w")
                json.dump(storage_state, tmp)
                tmp.close()
                context_kwargs["storage_state"] = tmp.name

            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()

            filled_count = 0
            screenshot_path = None
            error = None

            try:
                if progress_cb:
                    await progress_cb(10, f"Navigating to form: {portal_url}")

                await page.goto(portal_url, timeout=self.timeout)
                await page.wait_for_load_state("networkidle", timeout=self.timeout)

                if progress_cb:
                    await progress_cb(30, "Analyzing form fields")

                for field_selector, value in form_data.items():
                    try:
                        element = await page.query_selector(field_selector)
                        if not element:
                            continue
                        tag = (await element.get_attribute("type") or "").lower()
                        elem_tag = (await element.evaluate("el => el.tagName")).lower()

                        if elem_tag == "select":
                            await element.select_option(value=str(value))
                        elif tag in ("checkbox", "radio"):
                            if value:
                                await element.check()
                        elif tag == "file":
                            pass  # Skip file inputs
                        else:
                            await element.fill(str(value))

                        filled_count += 1
                    except Exception:
                        continue

                if progress_cb:
                    await progress_cb(80, f"Filled {filled_count} fields — taking screenshot")

                os.makedirs(settings.SCREENSHOT_DIR, exist_ok=True)
                screenshot_path = os.path.join(
                    settings.SCREENSHOT_DIR, f"form_filled_{os.getpid()}.png"
                )
                await page.screenshot(path=screenshot_path, full_page=True)

            except Exception as exc:
                error = str(exc)
                try:
                    screenshot_path = os.path.join(
                        settings.SCREENSHOT_DIR, f"form_error_{os.getpid()}.png"
                    )
                    await page.screenshot(path=screenshot_path)
                except Exception:
                    pass
            finally:
                await browser.close()

            return {"filled_count": filled_count, "screenshot": screenshot_path, "error": error}
