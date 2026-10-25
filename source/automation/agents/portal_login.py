"""Portal login agent using Playwright.

New-browser flow (Login.gov):
  1. Try persistent OpenClaw Chrome profile in headless mode.
  2. If Login.gov security check is detected (new device not recognized):
       - Open a VISIBLE browser window with the same profile.
       - Auto-fill credentials again.
       - Call `on_device_auth()` so the orchestrator marks the job as awaiting_approval.
       - Poll the page URL every 2 s for up to 5 minutes waiting for the user to
         complete the security check on their desktop.
       - On success the profile now holds device-trust cookies; future logins are
         fully automated.
  3. If 2FA is required, call `get_totp_code()` which blocks on the orchestrator queue.
"""
import asyncio
import os
import sys
from typing import Optional, Callable, Awaitable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
from config import settings

# ── Portal configuration ───────────────────────────────────────────────────────
# Grants.gov now uses Login.gov (federal SSO) for applicants.
# The "username" field is the Login.gov EMAIL; "password" is the Login.gov password.
PORTAL_CONFIGS = {
    "grants_gov": {
        "url": "https://apply07.grants.gov/apply/login.faces",
        "flow": "logingov",
        "logingov_btn_selector": "#form\\:loginGovLoginBtn",
        "logingov_email_selector": "#user_email",
        "logingov_password_selector": "input[type='password']",
        "logingov_submit_selector": "button[type='submit']",
        "post_login_url_fragment": "apply07.grants.gov",
        # One-time workspace linking: after first Login.gov auth, grants.gov asks to link
        # the Login.gov account to the legacy workspace (Workspace ID / password).
        "workspace_link_trigger": "federatedLogin",
        "workspace_username_selector": "input[id='Username'], input[name='Username'], input[type='text']",
        "workspace_password_selector": "input[type='password']",
        "workspace_submit_selector": "input[type='submit'], button[type='submit']",
    },
    "sam_gov": {
        "url": "https://sam.gov/sign-in",
        "flow": "logingov",
        "logingov_btn_selector": "a[href*='login.gov'], button[aria-label*='Login.gov']",
        "logingov_email_selector": "#user_email",
        "logingov_password_selector": "input[type='password']",
        "logingov_submit_selector": "button[type='submit']",
        "post_login_url_fragment": "sam.gov",
    },
    "justgrants": {
        "url": "https://justgrants.usdoj.gov/prweb/PRServletCustom?pyActivity=pyStartSession&StartTheApp=true",
        "flow": "direct",
        "username_selector": "#userName",
        "password_selector": "#Password",
        "submit_selector": ".login-button",
    },
    "foundation_center": {
        "url": "https://candid.org/login",
        "flow": "direct",
        "username_selector": "#edit-name",
        "password_selector": "#edit-pass",
        "submit_selector": "#edit-submit",
    },
}

# Path to the persistent OpenClaw Chrome profile
_OPENCLAW_PROFILE = os.getenv('GFM_BROWSER_PROFILE_DIR') or os.path.normpath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "..",
        "openclaw_login_agent_data", "_trusted_chrome_profile",
    )
)


class PortalLoginAgent:
    def __init__(self):
        self.headless = settings.PLAYWRIGHT_HEADLESS
        self.timeout = settings.AUTOMATION_TIMEOUT_MS

    def _screenshot_path(self, label: str) -> str:
        scr_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "backend",
            settings.SCREENSHOT_DIR,
        )
        os.makedirs(scr_dir, exist_ok=True)
        return os.path.join(scr_dir, f"{label}_{os.getpid()}.png")

    # ── Public entry point ─────────────────────────────────────────────────────
    async def login(
        self,
        portal_key: str,
        username: str,
        password: str,
        progress_cb: Optional[Callable] = None,
        get_totp_code: Optional[Callable[[], Awaitable[Optional[str]]]] = None,
        on_device_auth: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> dict:
        """
        Attempt login to the specified portal.

        Callbacks (all optional, all async):
          progress_cb(pct, message)   — progress updates
          get_totp_code()             — called when 2FA is needed; should block until
                                        the user supplies the code (via queue)
          on_device_auth(message)     — called when a new-device security check is
                                        detected; lets the orchestrator update job status
        """
        config = PORTAL_CONFIGS.get(portal_key)
        if not config:
            return {"success": False, "error": f"Unknown portal: {portal_key}", "step": "config"}

        flow = config.get("flow", "direct")

        if flow == "logingov":
            return await self._login_logingov(
                portal_key, config, username, password,
                progress_cb, get_totp_code, on_device_auth,
            )
        else:
            return await self._login_direct(
                portal_key, config, username, password, progress_cb,
            )

    # ── Login.gov flow ─────────────────────────────────────────────────────────
    async def _login_logingov(
        self,
        portal_key: str,
        config: dict,
        username: str,
        password: str,
        progress_cb,
        get_totp_code,
        on_device_auth,
    ) -> dict:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout

        # Always start with headless attempt using the persistent profile.
        result = await self._attempt_logingov(
            portal_key, config, username, password,
            progress_cb, get_totp_code, headless=self.headless,
        )

        # ── Security check (new device) ────────────────────────────────────────
        if result.get("requires_device_auth"):
            # Notify the orchestrator so it can mark the job as awaiting_approval
            if on_device_auth:
                await on_device_auth(
                    "Login.gov flagged this as a new device. "
                    "A browser window will open on your desktop — complete the security check there."
                )
            # Retry in VISIBLE mode so the user can interact with the browser
            result = await self._attempt_logingov(
                portal_key, config, username, password,
                progress_cb, get_totp_code, headless=False,
                wait_for_user=True,           # poll URL instead of failing immediately
            )

        return result

    async def _attempt_logingov(
        self,
        portal_key: str,
        config: dict,
        username: str,
        password: str,
        progress_cb,
        get_totp_code,
        headless: bool = True,
        wait_for_user: bool = False,
    ) -> dict:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout

        use_profile = os.path.isdir(_OPENCLAW_PROFILE)
        screenshot_path = None

        async def snap(label: str, page) -> str:
            path = self._screenshot_path(label)
            try:
                await page.screenshot(path=path, full_page=False)
            except Exception:
                pass
            return path

        async with async_playwright() as pw:
            context = None
            browser = None
            page = None

            try:
                # ── Launch browser ─────────────────────────────────────────────
                launch_args = [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                ]
                if use_profile:
                    try:
                        # Prefer installed Google Chrome for full profile compatibility
                        context = await pw.chromium.launch_persistent_context(
                            user_data_dir=_OPENCLAW_PROFILE,
                            headless=headless,
                            channel="chrome",
                            args=launch_args,
                            ignore_https_errors=True,
                        )
                    except Exception:
                        # Fallback: Playwright's own Chromium with the profile
                        try:
                            context = await pw.chromium.launch_persistent_context(
                                user_data_dir=_OPENCLAW_PROFILE,
                                headless=headless,
                                args=launch_args,
                                ignore_https_errors=True,
                            )
                        except Exception:
                            use_profile = False

                if not use_profile or context is None:
                    browser = await pw.chromium.launch(headless=headless, args=launch_args)
                    context = await browser.new_context(
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0.0.0 Safari/537.36"
                        ),
                        viewport={"width": 1280, "height": 800},
                    )

                # Mask webdriver flag
                await context.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
                )
                page = await context.new_page()

                # ── Step 1: Navigate to portal ─────────────────────────────────
                if progress_cb:
                    await progress_cb(10, f"Navigating to {portal_key}")
                await page.goto(config["url"], timeout=self.timeout)
                await page.wait_for_load_state("domcontentloaded", timeout=self.timeout)
                await asyncio.sleep(2)

                # ── Step 2: Click Login.gov button ─────────────────────────────
                if progress_cb:
                    await progress_cb(20, "Clicking Login.gov button")
                try:
                    await page.click(config["logingov_btn_selector"], timeout=15000)
                except PWTimeout:
                    screenshot_path = await snap(f"login_{portal_key}_no_logingov_btn", page)
                    return {
                        "success": False,
                        "error": "Login.gov button not found on portal page. The portal layout may have changed.",
                        "step": "click_logingov_btn",
                        "screenshot": screenshot_path,
                        "url": page.url,
                    }

                # ── Step 3: Wait for login.gov ─────────────────────────────────
                if progress_cb:
                    await progress_cb(30, "Redirecting to Login.gov")
                try:
                    await page.wait_for_url("**secure.login.gov**", timeout=20000)
                except PWTimeout:
                    pass
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
                await asyncio.sleep(1.5)
                screenshot_path = await snap(f"login_{portal_key}_at_logingov", page)

                _cur = page.url
                _workspace_trigger = config.get("workspace_link_trigger", "")

                # Workspace linking page? (federatedLogin — fill workspace creds first)
                if _workspace_trigger and _workspace_trigger in _cur:
                    if progress_cb:
                        await progress_cb(65, "Linking Login.gov to Grants.gov workspace account")
                    ws_username = getattr(settings, "GRANTS_GOV_WORKSPACE_USERNAME", None) or ""
                    ws_password = getattr(settings, "GRANTS_GOV_WORKSPACE_PASSWORD", None) or ""
                    if ws_username and ws_password:
                        try:
                            await page.fill(config["workspace_username_selector"], ws_username, timeout=8000)
                            await page.fill(config["workspace_password_selector"], ws_password, timeout=8000)
                            await page.click(config["workspace_submit_selector"], timeout=8000)
                            await page.wait_for_load_state("domcontentloaded", timeout=15000)
                            await asyncio.sleep(2)
                            screenshot_path = await snap(f"login_{portal_key}_workspace_linked", page)
                            if progress_cb:
                                await progress_cb(85, "Workspace linked — finalizing")
                            # Fall through to success check below
                        except Exception as link_err:
                            screenshot_path = await snap(f"login_{portal_key}_workspace_link_err", page)
                            return {
                                "success": False,
                                "error": f"Workspace linking failed: {link_err}",
                                "step": "workspace_link",
                                "screenshot": screenshot_path,
                            }
                    else:
                        screenshot_path = await snap(f"login_{portal_key}_workspace_link_needed", page)
                        return {
                            "success": False,
                            "needs_workspace_link": True,
                            "error": (
                                "Set GRANTS_GOV_WORKSPACE_USERNAME and GRANTS_GOV_WORKSPACE_PASSWORD in .env."
                            ),
                            "step": "workspace_link_needed",
                            "screenshot": screenshot_path,
                        }
                    # After linking, skip remaining login steps and go to final check
                    _skip_login_form = True
                else:
                    _skip_login_form = False

                # Already fully logged in? (not a linking page)
                if not _skip_login_form and config.get("post_login_url_fragment", "") in _cur:
                    if progress_cb:
                        await progress_cb(100, "Already signed in via saved session")
                    return {
                        "success": True,
                        "portal_key": portal_key,
                        "final_url": _cur,
                        "step": "complete",
                        "screenshot": screenshot_path,
                    }

                # Device remembered — Login.gov jumped straight to 2FA, skip email/password
                if not _skip_login_form and ("two_factor" in page.url or "otp" in page.url):
                    if progress_cb:
                        await progress_cb(63, "Device remembered — waiting for 2FA code")
                    screenshot_path = await snap(f"login_{portal_key}_direct_2fa", page)
                    # Fall through to 2FA block below (skips email/password)
                    goto_2fa = True
                else:
                    goto_2fa = False

                if not goto_2fa and not _skip_login_form:
                    # ── Step 4: Fill email ──────────────────────────────────────
                    if progress_cb:
                        await progress_cb(35, "Entering Login.gov email")
                    try:
                        await page.fill(config["logingov_email_selector"], username, timeout=12000)
                    except PWTimeout:
                        screenshot_path = await snap(f"login_{portal_key}_no_email_field", page)
                        return {
                            "success": False,
                            "error": f"Email field not found. URL: {page.url}",
                            "step": "fill_email",
                            "screenshot": screenshot_path,
                        }

                    # ── Step 5: Fill password ───────────────────────────────────
                    if progress_cb:
                        await progress_cb(50, "Entering password")
                    try:
                        await page.fill(config["logingov_password_selector"], password, timeout=10000)
                    except PWTimeout:
                        screenshot_path = await snap(f"login_{portal_key}_no_password_field", page)
                        return {
                            "success": False,
                            "error": f"Password field not found. URL: {page.url}",
                            "step": "fill_password",
                            "screenshot": screenshot_path,
                        }

                    # ── Step 6: Submit ──────────────────────────────────────────
                    if progress_cb:
                        await progress_cb(60, "Submitting Login.gov form")
                    await page.click(config["logingov_submit_selector"], timeout=10000)
                    await page.wait_for_load_state("domcontentloaded", timeout=20000)
                    await asyncio.sleep(2)
                    screenshot_path = await snap(f"login_{portal_key}_post_submit", page)

                # ── Detect post-login state ─────────────────────────────────────
                current_url = page.url

                # Security check (new device not recognized by Login.gov)
                if "security_check_failed" in current_url or "security_check" in current_url:
                    screenshot_path = await snap(f"login_{portal_key}_security_check", page)

                    if wait_for_user:
                        # Visible browser — wait for user to complete the security check
                        if progress_cb:
                            await progress_cb(
                                62,
                                "Waiting for device verification — complete the security check "
                                "in the browser window on your desktop",
                            )
                        success = await self._poll_until_portal(
                            page,
                            target_fragment=config.get("post_login_url_fragment", ""),
                            timeout=300,
                        )
                        if not success:
                            screenshot_path = await snap(f"login_{portal_key}_device_auth_timeout", page)
                            return {
                                "success": False,
                                "requires_device_auth": True,
                                "error": "Device verification timed out (5 min). Try connecting again.",
                                "step": "device_auth_timeout",
                                "screenshot": screenshot_path,
                            }
                        # Fell through — user completed verification, now at grants.gov
                        final_url = page.url
                        screenshot_path = await snap(f"login_{portal_key}_final", page)
                        if progress_cb:
                            await progress_cb(100, "Login successful")
                        return {
                            "success": True,
                            "portal_key": portal_key,
                            "final_url": final_url,
                            "step": "complete",
                            "screenshot": screenshot_path,
                        }
                    else:
                        # Headless attempt — signal caller to retry in visible mode
                        return {
                            "success": False,
                            "requires_device_auth": True,
                            "error": (
                                "Login.gov security check: this device is not yet recognized. "
                                "A browser window will open for one-time device verification."
                            ),
                            "step": "device_auth_needed",
                            "screenshot": screenshot_path,
                        }

                # 2FA detection
                page_text = await page.evaluate("() => document.body.innerText.substring(0,600)")
                if (
                    "two_factor" in current_url
                    or "authentication" in current_url
                    or "one_time" in page_text.lower()
                    or "authenticator" in page_text.lower()
                    or "verification code" in page_text.lower()
                ):
                    if get_totp_code:
                        if progress_cb:
                            await progress_cb(65, "Waiting for 2FA code")
                        totp_code = await get_totp_code()
                        if totp_code:
                            if progress_cb:
                                await progress_cb(70, "Entering 2FA code")
                            try:
                                # Login.gov OTP input — avoid hidden[name='code'] by putting
                                # inputmode/placeholder selectors first.
                                otp_selector = (
                                    "input[inputmode='numeric']:not([type='hidden']), "
                                    "input[autocomplete='one-time-code']:not([type='hidden']), "
                                    "input[placeholder*='123456']:not([type='hidden']), "
                                    "input[type='tel']:not([type='hidden']), "
                                    "input[name='user[otp_attempt]']:not([type='hidden']), "
                                    "input[name='code']:not([type='hidden'])"
                                )
                                await page.fill(otp_selector, totp_code, timeout=12000)
                                await page.click(
                                    "button[type='submit'], input[type='submit']",
                                    timeout=8000,
                                )
                                await page.wait_for_load_state("domcontentloaded", timeout=12000)
                                await asyncio.sleep(2)
                                screenshot_path = await snap(f"login_{portal_key}_post_2fa", page)
                            except Exception as mfa_err:
                                screenshot_path = await snap(f"login_{portal_key}_2fa_error", page)
                                return {
                                    "success": False,
                                    "error": f"2FA entry failed: {mfa_err}",
                                    "step": "2fa",
                                    "screenshot": screenshot_path,
                                }
                    else:
                        screenshot_path = await snap(f"login_{portal_key}_needs_2fa", page)
                        return {
                            "success": False,
                            "requires_2fa": True,
                            "error": "2FA code required. Enter it on the Providers page.",
                            "step": "2fa_needed",
                            "screenshot": screenshot_path,
                            "current_url": page.url,
                        }

                # ── Final: check success ───────────────────────────────────────
                if progress_cb:
                    await progress_cb(85, "Checking login result")
                final_url = page.url
                screenshot_path = await snap(f"login_{portal_key}_final", page)
                post_fragment = config.get("post_login_url_fragment", portal_key.replace("_", "."))
                logged_in = post_fragment in final_url
                if progress_cb:
                    await progress_cb(100, "Login successful" if logged_in else "Login may have failed")
                return {
                    "success": logged_in,
                    "portal_key": portal_key,
                    "final_url": final_url,
                    "screenshot": screenshot_path,
                    "error": (
                        None if logged_in
                        else f"Login did not redirect back to portal. Final URL: {final_url}"
                    ),
                    "step": "complete",
                }

            except Exception as exc:
                if page:
                    screenshot_path = await snap(f"login_{portal_key}_exception", page)
                return {
                    "success": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "step": "exception",
                    "screenshot": screenshot_path,
                    "url": page.url if page else None,
                }
            finally:
                if browser:
                    await browser.close()
                elif context:
                    await context.close()

    async def _poll_until_portal(self, page, target_fragment: str, timeout: int = 300) -> bool:
        """Poll page.url every 2 s until target_fragment appears. Returns True on success."""
        elapsed = 0
        while elapsed < timeout:
            try:
                if target_fragment and target_fragment in page.url:
                    return True
                # Also consider success if we landed on any grants.gov page after security check
                if "grants.gov" in page.url and "security_check" not in page.url:
                    return True
            except Exception:
                pass
            await asyncio.sleep(2)
            elapsed += 2
        return False

    # ── Direct username/password flow ──────────────────────────────────────────
    async def _login_direct(
        self,
        portal_key: str,
        config: dict,
        username: str,
        password: str,
        progress_cb,
    ) -> dict:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout

        screenshot_path = None
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
            context = await browser.new_context()
            page = await context.new_page()
            try:
                if progress_cb:
                    await progress_cb(10, f"Navigating to {portal_key}")
                await page.goto(config["url"], timeout=self.timeout)
                await page.wait_for_load_state("domcontentloaded", timeout=self.timeout)

                if progress_cb:
                    await progress_cb(30, "Entering credentials")
                if config.get("username_selector"):
                    await page.fill(config["username_selector"], username, timeout=10000)
                if config.get("password_selector") and password:
                    await page.fill(config["password_selector"], password, timeout=10000)

                if progress_cb:
                    await progress_cb(60, "Submitting form")
                await page.click(config["submit_selector"], timeout=10000)
                await page.wait_for_load_state("domcontentloaded", timeout=self.timeout)

                if progress_cb:
                    await progress_cb(85, "Checking login result")
                final_url = page.url

                async def snap(label):
                    path = self._screenshot_path(label)
                    try:
                        await page.screenshot(path=path, full_page=False)
                    except Exception:
                        pass
                    return path

                screenshot_path = await snap(f"login_{portal_key}_final")
                post_fragment = config.get("post_login_url_fragment", portal_key.replace("_", "."))
                logged_in = post_fragment in final_url if post_fragment else True
                if progress_cb:
                    await progress_cb(100, "Login successful" if logged_in else "Login may have failed")
                return {
                    "success": logged_in,
                    "portal_key": portal_key,
                    "final_url": final_url,
                    "screenshot": screenshot_path,
                    "error": None if logged_in else f"Login did not redirect back. Final URL: {final_url}",
                    "step": "complete",
                }
            except Exception as exc:
                return {
                    "success": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "step": "exception",
                    "url": page.url if page else None,
                }
            finally:
                await browser.close()
