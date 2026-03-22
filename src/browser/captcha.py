"""
CAPTCHA detection and wait helper.

When a CAPTCHA is detected on any page, the agent pauses and
waits for the user to solve it manually in the browser window.
"""
from __future__ import annotations

import asyncio
from typing import Callable

from playwright.async_api import Page

# Selectors that indicate a CAPTCHA is present
_CAPTCHA_SELECTORS = [
    'iframe[src*="recaptcha"]',
    'iframe[src*="hcaptcha"]',
    '.cf-challenge-running',
    '#cf-challenge-body',
    '.g-recaptcha',
    '#recaptcha',
    '[class*="captcha"]:not([class*="captcha-solved"])',
    '[id*="captcha"]:not([id*="captcha-solved"])',
    'iframe[title*="challenge"]',
]

_WAIT_POLL_SECONDS = 3.0
_WAIT_TIMEOUT_SECONDS = 300.0  # 5 minutes max


async def wait_if_captcha(
    page: Page,
    log_fn: Callable[[str], None] | None = None,
) -> None:
    """
    Check the current page for a CAPTCHA. If one is found, notify the user
    and wait (polling every 3 s) until it is solved or 5 minutes elapse.
    Safe to call at any point — does nothing if no CAPTCHA is present.
    """
    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)
        else:
            print(msg)

    # Quick check — is any CAPTCHA element visible?
    captcha_visible = False
    for selector in _CAPTCHA_SELECTORS:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                captcha_visible = True
                break
        except Exception:
            continue

    if not captcha_visible:
        return

    _log("CAPTCHA detected! Please solve it in the browser window. Waiting up to 5 minutes...")

    elapsed = 0.0
    while elapsed < _WAIT_TIMEOUT_SECONDS:
        await asyncio.sleep(_WAIT_POLL_SECONDS)
        elapsed += _WAIT_POLL_SECONDS

        still_present = False
        for selector in _CAPTCHA_SELECTORS:
            try:
                el = await page.query_selector(selector)
                if el and await el.is_visible():
                    still_present = True
                    break
            except Exception:
                continue

        if not still_present:
            _log("CAPTCHA solved — continuing.")
            return

    _log("CAPTCHA wait timed out after 5 minutes — continuing anyway.")
