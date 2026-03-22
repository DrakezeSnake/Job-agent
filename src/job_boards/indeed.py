"""
Indeed job board: search and apply.
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

BASE_URL = "https://www.indeed.com"


class Indeed(JobBoard):
    async def login(self) -> None:
        await self.page.goto(f"{BASE_URL}/account/login", wait_until="domcontentloaded")
        await human_delay(800, 1500)

        try:
            await self.page.wait_for_selector("#jobsearch-ViewjobPaneWrapper", timeout=3000)
            console.print("[green]Indeed: already logged in.[/green]")
            return
        except PWTimeout:
            pass

        await wait_if_captcha(self.page)

        # Google login
        if self.prefs.use_google_login:
            g = self.prefs.google_credentials
            if g.email and g.password:
                console.print("[cyan]Indeed: signing in with Google...[/cyan]")
                await click_google_button_and_login(self.page, g.email, g.password)
                await wait_if_captcha(self.page)
                console.print("[green]Indeed: logged in via Google.[/green]")
                return

        # Email / password login
        creds = self.prefs.get_credentials("indeed")
        if not creds.email or not creds.password:
            console.print("[yellow]Indeed credentials not set — skipping login.[/yellow]")
            return

        try:
            email_field = await self.page.query_selector('#login-email-input, input[name="__email"]')
            if email_field:
                await human_type(self.page, '#login-email-input, input[name="__email"]', creds.email)
                await human_delay(300, 600)
                await self.page.keyboard.press("Enter")
                await human_delay(800, 1500)
                await wait_if_captcha(self.page)

            pw_field = await self.page.query_selector('#login-password-input, input[name="__password"]')
            if pw_field:
                await human_type(self.page, '#login-password-input, input[name="__password"]', creds.password)
                await human_delay(300, 600)
                await self.page.keyboard.press("Enter")
                await self.page.wait_for_load_state("domcontentloaded")
                await human_delay(1500, 2500)
                await wait_if_captcha(self.page)

            console.print("[green]Indeed: logged in.[/green]")
        except Exception as e:
            console.print(f"[red]Indeed login error: {e}[/red]")

    async def search(self) -> list[JobListing]:
        jobs: list[JobListing] = []
        for title in self.prefs.job_titles:
            found = await self._search_title(title)
            jobs.extend(found)
        return jobs

    async def _search_title(self, title: str) -> list[JobListing]:
        params = urllib.parse.urlencode({
            "q": title,
            "l": self.prefs.location,
            "sort": "date",
        })
        url = f"{BASE_URL}/jobs?{params}"
        await self.page.goto(url, wait_until="domcontentloaded")
        await human_delay(1000, 2000)

        jobs: list[JobListing] = []
        for _ in range(3):
            cards = await self.page.query_selector_all('[data-testid="slider_item"], .job_seen_beacon')
            for card in cards:
                try:
                    title_el = await card.query_selector('[data-testid="jobTitle"] a, h2.jobTitle a')
                    company_el = await card.query_selector('[data-testid="company-name"], .companyName')
                    if not (title_el and company_el):
                        continue

                    job_title = (await title_el.inner_text()).strip()
                    company = (await company_el.inner_text()).strip()
                    href = await title_el.get_attribute("href") or ""
                    job_url = href if href.startswith("http") else BASE_URL + href

                    if company in self.prefs.blacklisted_companies:
                        continue

                    jobs.append(JobListing(
                        title=job_title,
                        company=company,
                        board="indeed",
                        url=job_url,
                    ))
                except Exception:
                    continue

            try:
                next_btn = await self.page.query_selector('[data-testid="pagination-page-next"]')
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

            # Get description
            try:
                desc_el = await self.page.query_selector('#jobDescriptionText')
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

            # Look for Indeed Apply button
            apply_btn = await self.page.query_selector('[id*="indeedApplyButton"], button[class*="apply"]')
            if apply_btn:
                return await self._indeed_apply_flow(job, resume_path, cover_letter_path)
            else:
                # External apply
                ext_btn = await self.page.query_selector('a[href*="clk?"], a[class*="applyButton"]')
                if ext_btn:
                    return await self._external_apply(job, resume_path, cover_letter_path, ext_btn)

            return ApplyResult(success=False, job_url=job.url, notes="No apply button found")
        except Exception as e:
            return ApplyResult(success=False, job_url=job.url, notes=str(e))

    async def _indeed_apply_flow(
        self,
        job: JobListing,
        resume_path: str,
        cover_letter_path: str,
    ) -> ApplyResult:
        try:
            await self.page.click('[id*="indeedApplyButton"], button[class*="apply"]')
            await human_delay(1000, 2000)

            # Handle iframe-based Indeed apply widget
            frame = None
            for f in self.page.frames:
                if "indeed.com" in f.url and "apply" in f.url:
                    frame = f
                    break

            target = frame or self.page
            max_steps = 10
            for _ in range(max_steps):
                # Upload resume
                file_input = await target.query_selector('input[type="file"]')
                if file_input and resume_path:
                    await file_input.set_input_files(resume_path)
                    await human_delay(500, 1000)

                # Answer questions
                await self._fill_indeed_questions(target)

                submit = await target.query_selector('button[type="submit"][data-testid*="submit"]')
                if submit:
                    await submit.click()
                    await human_delay(1500, 2500)
                    return ApplyResult(
                        success=True,
                        job_url=job.url,
                        resume_path=resume_path,
                        cover_letter_path=cover_letter_path,
                    )

                next_btn = await target.query_selector('button[data-testid*="next"], button:has-text("Continue")')
                if next_btn:
                    await next_btn.click()
                    await human_delay(700, 1200)
                else:
                    break

            return ApplyResult(success=False, job_url=job.url, notes="Could not complete Indeed apply flow")
        except Exception as e:
            return ApplyResult(success=False, job_url=job.url, notes=f"Indeed apply error: {e}")

    async def _fill_indeed_questions(self, target) -> None:
        inputs = await target.query_selector_all('input[type="text"], input[type="number"], textarea')
        for inp in inputs:
            try:
                current = await inp.input_value()
                if current:
                    continue
                # Try to find associated label
                inp_id = await inp.get_attribute("id") or ""
                label_el = await target.query_selector(f'label[for="{inp_id}"]') if inp_id else None
                question = (await label_el.inner_text()).strip() if label_el else inp_id
                if question:
                    answer = await self._answer_form_question(question)
                    await inp.fill(answer)
                    await human_delay(200, 500)
            except Exception:
                continue

    async def _external_apply(self, job, resume_path, cover_letter_path, btn) -> ApplyResult:
        try:
            async with self.page.context.expect_page() as new_page_info:
                await btn.click()
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
            return ApplyResult(success=False, job_url=job.url, notes=f"External apply error: {e}")
