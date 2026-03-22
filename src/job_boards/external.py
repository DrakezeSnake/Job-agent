"""
Generic handler for external company application websites.
Best-effort: fills text inputs, uploads resume, answers questions via QA memory.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.browser.browser_manager import human_delay

if TYPE_CHECKING:
    from playwright.async_api import Page

    from src.job_boards.base import JobListing
    from src.memory.qa_memory import QAMemory


async def apply_on_external_site(
    page: "Page",
    job: "JobListing",
    resume_path: str,
    cover_letter_path: str,
    qa_memory: "QAMemory",
) -> bool:
    """
    Attempt to fill and submit an application on an external company site.
    Returns True if submission appears successful, False otherwise.
    """
    try:
        await human_delay(1000, 2000)

        # Upload resume if a file input exists
        file_input = await page.query_selector('input[type="file"]')
        if file_input and resume_path:
            await file_input.set_input_files(resume_path)
            await human_delay(500, 1500)

        # Fill text/email/tel inputs that are empty
        inputs = await page.query_selector_all(
            'input[type="text"], input[type="email"], input[type="tel"], input[type="number"], textarea'
        )
        for inp in inputs:
            try:
                current = await inp.input_value()
                if current:
                    continue
                inp_id = await inp.get_attribute("id") or ""
                placeholder = await inp.get_attribute("placeholder") or ""
                name_attr = await inp.get_attribute("name") or ""
                label_el = await page.query_selector(f'label[for="{inp_id}"]') if inp_id else None
                question = (
                    (await label_el.inner_text()).strip()
                    if label_el
                    else (placeholder or name_attr)
                )
                if not question:
                    continue
                answer = await qa_memory.get_or_ask(question)
                await inp.fill(answer)
                await human_delay(100, 300)
            except Exception:
                continue

        # Fill cover letter textarea if detected
        cl_fields = await page.query_selector_all(
            'textarea[name*="cover"], textarea[id*="cover"], textarea[placeholder*="cover"]'
        )
        for field in cl_fields:
            try:
                current = await field.input_value()
                if not current and cover_letter_path:
                    txt_path = cover_letter_path.replace(".pdf", ".txt")
                    try:
                        import aiofiles
                        async with aiofiles.open(txt_path) as f:
                            cl_text = await f.read()
                        await field.fill(cl_text)
                        await human_delay(300, 600)
                    except Exception:
                        pass
            except Exception:
                continue

        # Submit
        submit_btn = await page.query_selector(
            'button[type="submit"], input[type="submit"], button:has-text("Submit"), button:has-text("Apply")'
        )
        if submit_btn:
            await submit_btn.click()
            await human_delay(2000, 3500)
            return True

        return False
    except Exception:
        return False
