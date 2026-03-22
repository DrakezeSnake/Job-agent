"""
Shared Google OAuth helper used by all job board login methods.
"""
from __future__ import annotations

from typing import Callable

from playwright.async_api import Page, TimeoutError as PWTimeout

from src.browser.browser_manager import human_delay, human_type
from src.browser.captcha import wait_if_captcha


async def google_login(
    page: Page,
    email: str,
    password: str,
    log_fn: Callable[[str], None] | None = None,
) -> None:
    """
    Complete a Google sign-in flow on the given page.
    Expects the page to already be navigated to accounts.google.com.
    """
    try:
        await page.wait_for_url("*accounts.google.com*", timeout=10_000)
    except PWTimeout:
        pass

    await human_delay(500, 1000)
    await wait_if_captcha(page, log_fn)

    # Fill email
    await page.wait_for_selector('input[type="email"]', state="visible", timeout=8000)
    await human_type(page, 'input[type="email"]', email)
    await human_delay(300, 600)

    # Click Next after email
    await page.click("#identifierNext, button[jsname='LgbsSe']")
    await human_delay(800, 1500)
    await wait_if_captcha(page, log_fn)

    # Fill password
    await page.wait_for_selector('input[type="password"]', state="visible", timeout=8000)
    await human_type(page, 'input[type="password"]', password)
    await human_delay(300, 600)

    # Click Next after password
    await page.click("#passwordNext, button[jsname='LgbsSe']")
    await page.wait_for_load_state("domcontentloaded")
    await human_delay(1500, 2500)


async def click_google_button_and_login(
    page: Page,
    email: str,
    password: str,
    log_fn: Callable[[str], None] | None = None,
) -> None:
    """
    Click the "Continue with Google" / "Sign in with Google" button on a
    job-board login page, then handle either a popup or redirect OAuth flow.
    """
    GOOGLE_BTN = (
        'button:has-text("Continue with Google"), '
        'a:has-text("Continue with Google"), '
        'button:has-text("Sign in with Google"), '
        'a:has-text("Sign in with Google"), '
        '[data-provider="google"], '
        '[data-litms-control-urn*="google"]'
    )

    try:
        # Some boards open Google auth in a new popup window
        async with page.context.expect_page(timeout=4000) as popup_info:
            await page.click(GOOGLE_BTN)
        popup = await popup_info.value
        await popup.wait_for_load_state("domcontentloaded")
        await google_login(popup, email, password, log_fn)
        try:
            await popup.wait_for_close(timeout=15_000)
        except PWTimeout:
            pass
    except Exception:
        # Redirect flow — Google auth happens in the same tab
        try:
            await page.click(GOOGLE_BTN)
            await google_login(page, email, password, log_fn)
        except Exception:
            pass
