"""
LinkedIn job board: search and apply (Easy Apply + external).
"""
from __future__ import annotations

import asyncio
import urllib.parse
from typing import TYPE_CHECKING

from playwright.async_api import Page, TimeoutError as PWTimeout
from rich.console import Console

from src.browser.browser_manager import human_delay, human_type
from src.browser.captcha import wait_if_captcha
from src.browser.google_auth import click_google_button_and_login
from src.job_boards.base import ApplyResult, JobBoard, JobListing

if TYPE_CHECKING:
    pass

console = Console()

BASE_URL = "https://www.linkedin.com"


class LinkedIn(JobBoard):
    async def login(self) -> None:
        await self.page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
        await human_delay(800, 1500)

        try:
            await self.page.wait_for_selector("#global-nav", timeout=3000)
            console.print("[green]LinkedIn: already logged in.[/green]")
            return
        except PWTimeout:
            pass

        await wait_if_captcha(self.page)

        # Google login
        if self.prefs.use_google_login:
            g = self.prefs.google_credentials
            if g.email and g.password:
                console.print("[cyan]LinkedIn: signing in with Google...[/cyan]")
                await click_google_button_and_login(self.page, g.email, g.password)
                await wait_if_captcha(self.page)
                console.print("[green]LinkedIn: logged in via Google.[/green]")
                return

        # Email / password login
        creds = self.prefs.get_credentials("linkedin")
        if not creds.email or not creds.password:
            console.print("[yellow]LinkedIn credentials not set — skipping login.[/yellow]")
            return

        await human_type(self.page, "#username", creds.email)
        await human_delay(300, 700)
        await human_type(self.page, "#password", creds.password)
        await human_delay(300, 600)
        await self.page.click('[type="submit"]')
        await self.page.wait_for_load_state("domcontentloaded")
        await human_delay(1500, 3000)
        await wait_if_captcha(self.page)
        console.print("[green]LinkedIn: logged in.[/green]")

    async def search(self) -> list[JobListing]:
        jobs: list[JobListing] = []
        for title in self.prefs.job_titles:
            found = await self._search_title(title)
            jobs.extend(found)
        return jobs

    async def _search_title(self, title: str) -> list[JobListing]:
        params = urllib.parse.urlencode({
            "keywords": title,
            "location": self.prefs.location,
            "f_LF": "f_AL",          # Easy Apply filter
            "sortBy": "R",            # Most relevant
        })
        url = f"{BASE_URL}/jobs/search/?{params}"
        await self.page.goto(url, wait_until="domcontentloaded")
        await human_delay(1000, 2000)

        jobs: list[JobListing] = []
        for _ in range(3):  # paginate up to 3 pages
            cards = await self.page.query_selector_all(".job-card-container")
            for card in cards:
                try:
                    title_el = await card.query_selector(".job-card-list__title")
                    company_el = await card.query_selector(".job-card-container__primary-description")
                    link_el = await card.query_selector("a.job-card-container__link")

                    if not (title_el and company_el and link_el):
                        continue

                    job_title = (await title_el.inner_text()).strip()
                    company = (await company_el.inner_text()).strip()
                    href = await link_el.get_attribute("href") or ""
                    job_url = href.split("?")[0] if href.startswith("http") else BASE_URL + href.split("?")[0]

                    # Skip blacklisted companies
                    if company in self.prefs.blacklisted_companies:
                        continue

                    jobs.append(JobListing(
                        title=job_title,
                        company=company,
                        board="linkedin",
                        url=job_url,
                    ))
                except Exception:
                    continue

            # Try next page
            try:
                next_btn = await self.page.query_selector('button[aria-label="View next page"]')
                if next_btn:
                    await next_btn.click()
                    await human_delay(1500, 2500)
                else:
                    break
            except Exception:
                break

        return jobs

    async def _get_description(self) -> str:
        try:
            el = await self.page.query_selector(".jobs-description__content")
            if el:
                return (await el.inner_text()).strip()
        except Exception:
            pass
        return ""

    async def apply(
        self,
        job: JobListing,
        resume_path: str,
        cover_letter_path: str,
    ) -> ApplyResult:
        try:
            await self.page.goto(job.url, wait_until="domcontentloaded")
            await human_delay(1000, 2000)

            job.description = await self._get_description()

            # Detect Easy Apply button
            easy_apply_btn = await self.page.query_selector('[aria-label*="Easy Apply"]')
            if easy_apply_btn:
                return await self._easy_apply(job, resume_path, cover_letter_path)
            else:
                return await self._external_apply(job, resume_path, cover_letter_path)

        except Exception as e:
            return ApplyResult(success=False, job_url=job.url, notes=str(e))

    async def _easy_apply(
        self,
        job: JobListing,
        resume_path: str,
        cover_letter_path: str,
    ) -> ApplyResult:
        if self.dry_run:
            return ApplyResult(
                success=True,
                job_url=job.url,
                resume_path=resume_path,
                cover_letter_path=cover_letter_path,
                notes="dry_run",
            )

        try:
            await self.page.click('[aria-label*="Easy Apply"]')
            await human_delay(800, 1500)

            # Walk through multi-step Easy Apply modal
            max_steps = 15
            for _ in range(max_steps):
                await self._fill_easy_apply_step(resume_path, cover_letter_path)

                # Check for Submit button
                submit_btn = await self.page.query_selector('button[aria-label*="Submit application"]')
                if submit_btn:
                    await submit_btn.click()
                    await human_delay(1500, 2500)
                    return ApplyResult(
                        success=True,
                        job_url=job.url,
                        resume_path=resume_path,
                        cover_letter_path=cover_letter_path,
                    )

                # Check for Next / Review button
                next_btn = await self.page.query_selector('button[aria-label="Continue to next step"]')
                review_btn = await self.page.query_selector('button[aria-label="Review your application"]')
                btn = next_btn or review_btn
                if btn:
                    await btn.click()
                    await human_delay(700, 1200)
                else:
                    break

            return ApplyResult(success=False, job_url=job.url, notes="Could not complete Easy Apply steps")
        except Exception as e:
            return ApplyResult(success=False, job_url=job.url, notes=f"Easy Apply error: {e}")

    async def _fill_easy_apply_step(self, resume_path: str, cover_letter_path: str) -> None:
        # Upload resume if file input is present
        file_input = await self.page.query_selector('input[type="file"]')
        if file_input and resume_path:
            try:
                await file_input.set_input_files(resume_path)
                await human_delay(500, 1000)
            except Exception:
                pass

        # Fill cover letter textarea if present
        cl_textarea = await self.page.query_selector('textarea[id*="cover-letter"], textarea[name*="cover"]')
        if cl_textarea and cover_letter_path:
            try:
                import aiofiles
                async with aiofiles.open(cover_letter_path.replace(".pdf", ".txt"), "r") as f:
                    cl_text = await f.read()
                await cl_textarea.fill(cl_text)
                await human_delay(300, 700)
            except Exception:
                pass

        # Answer any visible questions
        await self._answer_visible_questions()

    async def _answer_visible_questions(self) -> None:
        """Find form labels and fill in answers using QA memory."""
        labels = await self.page.query_selector_all(".jobs-easy-apply-form-element")
        for element in labels:
            try:
                label_el = await element.query_selector("label, legend")
                if not label_el:
                    continue
                question_text = (await label_el.inner_text()).strip()
                if not question_text:
                    continue

                # Determine input type
                text_input = await element.query_selector('input[type="text"], input[type="number"], input[type="email"]')
                textarea = await element.query_selector("textarea")
                select_el = await element.query_selector("select")
                radio_group = await element.query_selector_all('input[type="radio"]')

                if text_input or textarea:
                    current = await (text_input or textarea).input_value()
                    if not current:
                        answer = await self._answer_form_question(question_text, "text")
                        await (text_input or textarea).fill(answer)
                        await human_delay(200, 500)

                elif select_el:
                    answer = await self._answer_form_question(question_text, "select")
                    await select_el.select_option(label=answer)
                    await human_delay(200, 400)

                elif radio_group:
                    answer = await self._answer_form_question(question_text, "radio")
                    for radio in radio_group:
                        val = await radio.get_attribute("value") or ""
                        lbl = await radio.evaluate("el => el.labels[0]?.innerText || ''")
                        if answer.lower() in (val.lower(), lbl.lower()):
                            await radio.click()
                            await human_delay(200, 400)
                            break

            except Exception:
                continue

    async def _external_apply(
        self,
        job: JobListing,
        resume_path: str,
        cover_letter_path: str,
    ) -> ApplyResult:
        """Click the external Apply button and handle the new page/tab."""
        if self.dry_run:
            return ApplyResult(
                success=True,
                job_url=job.url,
                resume_path=resume_path,
                cover_letter_path=cover_letter_path,
                notes="dry_run_external",
            )

        try:
            apply_btn = await self.page.query_selector('[data-control-name="jobdetails_topcard_inapply"]')
            if not apply_btn:
                apply_btn = await self.page.query_selector('a.jobs-apply-button')
            if not apply_btn:
                return ApplyResult(success=False, job_url=job.url, notes="No apply button found")

            async with self.page.context.expect_page() as new_page_info:
                await apply_btn.click()
            external_page = await new_page_info.value
            await external_page.wait_for_load_state("domcontentloaded")
            job.external_url = external_page.url

            # Delegate to generic external handler
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
            return ApplyResult(success=False, job_url=job.url, notes=f"External apply error: {e}")
