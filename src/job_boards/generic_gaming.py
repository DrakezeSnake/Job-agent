"""
GenericGamingBoard: reusable base class for gaming job boards.

Most gaming job boards share the same flow:
  1. Browse job listings publicly (no login needed)
  2. Click Apply → redirect to the company's own ATS
  3. apply_on_external_site() handles the actual form submission

Subclasses only need to set class-level selector constants.
"""
from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING

from playwright.async_api import TimeoutError as PWTimeout

from src.browser.browser_manager import human_delay
from src.browser.captcha import wait_if_captcha
from src.job_boards.base import ApplyResult, JobBoard, JobListing

if TYPE_CHECKING:
    pass

# Common fallback selector chains used when board-specific selectors fail
_CARD_FALLBACKS = [
    "article", ".job", ".listing", ".vacancy",
    "[class*='job-card']", "[class*='job-item']", "[class*='job-listing']",
]
_TITLE_FALLBACKS = [
    "h2 a", "h3 a", "h4 a",
    ".job-title a", ".position a", ".title a", "[class*='title'] a",
    "h2", "h3",
]
_COMPANY_FALLBACKS = [
    ".company", ".employer", ".company-name", ".studio",
    "[class*='company']", "[class*='employer']", "[class*='studio']",
]
_APPLY_FALLBACKS = [
    'a[href*="apply"]',
    'a:has-text("Apply Now")',
    'a:has-text("Apply")',
    'button:has-text("Apply Now")',
    'button:has-text("Apply")',
    '[class*="apply"]',
    'a[rel="noopener"][target="_blank"]',  # many boards use this for external links
]


async def _try_selectors(element, selectors: list[str]) -> str:
    """Try a list of CSS selectors on an element; return inner_text of first match."""
    for sel in selectors:
        try:
            el = await element.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                if text:
                    return text
        except Exception:
            continue
    return ""


async def _try_href(element, selectors: list[str]) -> str:
    """Try a list of CSS selectors; return href of first <a> match."""
    for sel in selectors:
        try:
            el = await element.query_selector(sel)
            if el:
                href = await el.get_attribute("href") or ""
                if href:
                    return href
        except Exception:
            continue
    return ""


class GenericGamingBoard(JobBoard):
    """
    Base class for gaming-specific job boards.
    Subclasses configure class variables; no method overriding required.
    """

    # ── Subclass configuration ──────────────────────────────────────────────
    BASE_URL: str = ""
    # {query} and optionally {location} placeholders
    SEARCH_URL: str = ""
    BOARD_NAME: str = "gaming"   # used in JobListing.board field

    # CSS selectors — primary. Falls back to _*_FALLBACKS if empty or no match.
    CARD_SELECTOR: str = ""
    TITLE_SELECTOR: str = ""
    COMPANY_SELECTOR: str = ""
    LINK_SELECTOR: str = ""          # <a> with href on the card
    DESCRIPTION_SELECTOR: str = ""   # on job detail page
    APPLY_BTN_SELECTOR: str = ""     # on job detail page

    # ── Interface ───────────────────────────────────────────────────────────

    async def login(self) -> None:
        """No login required for gaming boards."""
        pass

    async def search(self) -> list[JobListing]:
        jobs: list[JobListing] = []
        for title in self.prefs.job_titles:
            url = self.SEARCH_URL.format(
                query=urllib.parse.quote_plus(title),
                location=urllib.parse.quote_plus(self.prefs.location),
            )
            try:
                await self.page.goto(url, wait_until="domcontentloaded")
                await human_delay(1500, 2500)
                await wait_if_captcha(self.page)
                found = await self._scrape_listings()
                jobs.extend(found)
            except Exception:
                continue
        return jobs

    async def apply(
        self,
        job: JobListing,
        resume_path: str,
        cover_letter_path: str,
    ) -> ApplyResult:
        try:
            await self.page.goto(job.url, wait_until="domcontentloaded")
            await human_delay(1000, 2000)
            await wait_if_captcha(self.page)

            # Scrape description
            if self.DESCRIPTION_SELECTOR:
                try:
                    desc_el = await self.page.query_selector(self.DESCRIPTION_SELECTOR)
                    if desc_el:
                        job.description = (await desc_el.inner_text()).strip()[:3000]
                except Exception:
                    pass

            if self.dry_run:
                return ApplyResult(
                    success=True,
                    job_url=job.url,
                    resume_path=resume_path,
                    cover_letter_path=cover_letter_path,
                    notes="dry_run",
                )

            apply_btn = await self._find_apply_btn()
            if not apply_btn:
                return ApplyResult(
                    success=False, job_url=job.url, notes="No apply button found"
                )

            # Click and handle popup or same-tab redirect
            ext_page = None
            try:
                async with self.page.context.expect_page(timeout=4000) as new_page_info:
                    await apply_btn.click()
                ext_page = await new_page_info.value
                await ext_page.wait_for_load_state("domcontentloaded")
            except Exception:
                # No popup — same tab redirect
                try:
                    await apply_btn.click()
                    await self.page.wait_for_load_state("domcontentloaded")
                    await human_delay(1000, 2000)
                except Exception:
                    pass
                ext_page = self.page

            job.external_url = ext_page.url
            await wait_if_captcha(ext_page)

            from src.job_boards.external import apply_on_external_site
            success = await apply_on_external_site(
                ext_page, job, resume_path, cover_letter_path, self.qa_memory
            )

            if ext_page is not self.page:
                try:
                    await ext_page.close()
                except Exception:
                    pass

            return ApplyResult(
                success=success,
                job_url=job.url,
                resume_path=resume_path,
                cover_letter_path=cover_letter_path,
                notes=f"external:{job.external_url}",
            )

        except Exception as e:
            return ApplyResult(success=False, job_url=job.url, notes=str(e))

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _scrape_listings(self) -> list[JobListing]:
        """Scrape job cards from the current page."""
        cards = []
        # Try primary card selector, then fallbacks
        selectors = (
            [self.CARD_SELECTOR] if self.CARD_SELECTOR else []
        ) + _CARD_FALLBACKS

        for sel in selectors:
            try:
                found = await self.page.query_selector_all(sel)
                if found:
                    cards = found
                    break
            except Exception:
                continue

        jobs: list[JobListing] = []
        for card in cards[:30]:  # cap at 30 per page
            try:
                # Title
                title_sels = (
                    [self.TITLE_SELECTOR] if self.TITLE_SELECTOR else []
                ) + _TITLE_FALLBACKS
                title = await _try_selectors(card, title_sels)
                if not title:
                    continue

                # Company
                company_sels = (
                    [self.COMPANY_SELECTOR] if self.COMPANY_SELECTOR else []
                ) + _COMPANY_FALLBACKS
                company = await _try_selectors(card, company_sels) or "Unknown"

                # Link href
                link_sels = (
                    [self.LINK_SELECTOR] if self.LINK_SELECTOR else []
                ) + ["a"]
                href = await _try_href(card, link_sels)
                if not href:
                    continue

                job_url = (
                    href if href.startswith("http")
                    else self.BASE_URL.rstrip("/") + "/" + href.lstrip("/")
                )

                if company in self.prefs.blacklisted_companies:
                    continue

                jobs.append(JobListing(
                    title=title,
                    company=company,
                    board=self.BOARD_NAME,
                    url=job_url,
                ))
            except Exception:
                continue

        return jobs

    async def _find_apply_btn(self):
        """Find the apply button using primary selector then fallbacks."""
        selectors = (
            [self.APPLY_BTN_SELECTOR] if self.APPLY_BTN_SELECTOR else []
        ) + _APPLY_FALLBACKS

        for sel in selectors:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    return el
            except Exception:
                continue
        return None
