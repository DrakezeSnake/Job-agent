"""
Glassdoor job board: search and apply.
"""
from __future__ import annotations

import urllib.parse

from playwright.async_api import TimeoutError as PWTimeout
from rich.console import Console

from src.browser.browser_manager import human_delay, human_type
from src.browser.captcha import wait_if_captcha
from src.browser.google_auth import click_google_button_and_login
from src.job_boards.base import ApplyResult, JobBoard, JobListing

console = Console()

BASE_URL = "https://www.glassdoor.com"


class Glassdoor(JobBoard):
    async def login(self) -> None:
        await self.page.goto(f"{BASE_URL}/profile/login_input.htm", wait_until="domcontentloaded")
        await human_delay(800, 1500)

        try:
            await self.page.wait_for_selector('[data-test="user-menu-trigger"]', timeout=3000)
            console.print("[green]Glassdoor: already logged in.[/green]")
            return
        except PWTimeout:
            pass

        await wait_if_captcha(self.page)

        # Google login
        if self.prefs.use_google_login:
            g = self.prefs.google_credentials
            if g.email and g.password:
                console.print("[cyan]Glassdoor: signing in with Google...[/cyan]")
                await click_google_button_and_login(self.page, g.email, g.password)
                await wait_if_captcha(self.page)
                console.print("[green]Glassdoor: logged in via Google.[/green]")
                return

        # Email / password login
        creds = self.prefs.get_credentials("glassdoor")
        if not creds.email or not creds.password:
            console.print("[yellow]Glassdoor credentials not set — skipping login.[/yellow]")
            return

        try:
            await human_type(self.page, '#userEmail', creds.email)
            await human_delay(300, 600)
            await self.page.click('[name="submit"]')
            await human_delay(800, 1500)
            await wait_if_captcha(self.page)
            await human_type(self.page, '#userPassword', creds.password)
            await human_delay(300, 600)
            await self.page.click('[name="submit"]')
            await self.page.wait_for_load_state("domcontentloaded")
            await human_delay(1500, 2500)
            await wait_if_captcha(self.page)
            console.print("[green]Glassdoor: logged in.[/green]")
        except Exception as e:
            console.print(f"[red]Glassdoor login error: {e}[/red]")

    async def search(self) -> list[JobListing]:
        jobs: list[JobListing] = []
        for title in self.prefs.job_titles:
            found = await self._search_title(title)
            jobs.extend(found)
        return jobs

    async def _search_title(self, title: str) -> list[JobListing]:
        params = urllib.parse.urlencode({
            "sc.keyword": title,
            "locT": "N",
            "locId": "1",
        })
        url = f"{BASE_URL}/Job/jobs.htm?{params}"
        await self.page.goto(url, wait_until="domcontentloaded")
        await human_delay(1000, 2000)

        jobs: list[JobListing] = []
        for _ in range(3):
            cards = await self.page.query_selector_all('[data-test="jobListing"], li.react-job-listing')
            for card in cards:
                try:
                    title_el = await card.query_selector('[data-test="job-title"], a.job-title')
                    company_el = await card.query_selector('[data-test="employer-name"], .employer-name')
                    link_el = await card.query_selector('a[href*="/job-listing/"]')
                    if not (title_el and company_el):
                        continue

                    job_title = (await title_el.inner_text()).strip()
                    company = (await company_el.inner_text()).strip()
                    href = (await link_el.get_attribute("href")) if link_el else ""
                    job_url = href if href.startswith("http") else BASE_URL + href

                    if company in self.prefs.blacklisted_companies:
                        continue

                    jobs.append(JobListing(
                        title=job_title,
                        company=company,
                        board="glassdoor",
                        url=job_url,
                    ))
                except Exception:
                    continue

            try:
                next_btn = await self.page.query_selector('[data-test="pagination-next"]')
                if next_btn:
                    await next_btn.click()
                    await human_delay(1500, 2500)
                else:
                    break
            except Exception:
                break

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

            try:
                desc_el = await self.page.query_selector('[data-test="jobDescriptionContent"], .desc')
                if desc_el:
                    job.description = (await desc_el.inner_text()).strip()
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

            apply_btn = await self.page.query_selector(
                '[data-test="applyButton"], button[class*="apply"], a[class*="apply"]'
            )
            if not apply_btn:
                return ApplyResult(success=False, job_url=job.url, notes="No apply button found")

            async with self.page.context.expect_page() as new_page_info:
                await apply_btn.click()
            external_page = await new_page_info.value
            await external_page.wait_for_load_state("domcontentloaded")
            job.external_url = external_page.url

            from src.job_boards.external import apply_on_external_site
            success = await apply_on_external_site(
                external_page, job, resume_path, cover_letter_path, self.qa_memory
            )
            await external_page.close()

            return ApplyResult(
                success=success,
                job_url=job.url,
                resume_path=resume_path,
                cover_letter_path=cover_letter_path,
                notes=f"external:{job.external_url}",
            )
        except Exception as e:
            return ApplyResult(success=False, job_url=job.url, notes=str(e))
