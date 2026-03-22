"""
Playwright browser lifecycle management with anti-detection measures.
"""
from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path
from typing import AsyncGenerator

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

# Common desktop user agents to rotate through
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# JavaScript to mask headless fingerprints
_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
"""


class BrowserManager:
    """
    Async context manager that owns a Playwright browser and context.
    Provides human-like delays and anti-bot stealth by default.
    """

    def __init__(
        self,
        headless: bool = False,
        session_path: Path | None = None,
    ) -> None:
        self.headless = headless
        self.session_path = session_path
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> "BrowserManager":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        storage_state = None
        if self.session_path and self.session_path.exists():
            storage_state = str(self.session_path)

        self._context = await self._browser.new_context(
            user_agent=random.choice(_USER_AGENTS),
            viewport={"width": 1280, "height": 800},
            storage_state=storage_state,
            locale="en-US",
            timezone_id="America/New_York",
        )
        await self._context.add_init_script(_STEALTH_SCRIPT)
        return self

    async def __aexit__(self, *_) -> None:
        if self._context and self.session_path:
            self.session_path.parent.mkdir(parents=True, exist_ok=True)
            await self._context.storage_state(path=str(self.session_path))
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def new_page(self) -> Page:
        assert self._context, "BrowserManager not started"
        page = await self._context.new_page()
        return page

    @property
    def context(self) -> BrowserContext:
        assert self._context, "BrowserManager not started"
        return self._context


async def human_delay(min_ms: int = 500, max_ms: int = 1500) -> None:
    """Random delay to simulate human behaviour."""
    await asyncio.sleep(random.randint(min_ms, max_ms) / 1000)


async def human_type(page: Page, selector: str, text: str) -> None:
    """Type text character by character with random delays."""
    await page.click(selector)
    for char in text:
        await page.keyboard.type(char)
        await asyncio.sleep(random.uniform(0.05, 0.18))
