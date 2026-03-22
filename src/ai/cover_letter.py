"""
Generates a tailored cover letter using the Claude API.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import anthropic

if TYPE_CHECKING:
    from src.job_boards.base import JobListing

SYSTEM_PROMPT = """\
You are a professional cover letter writer.
Write a concise, compelling cover letter (3 paragraphs maximum) tailored to
the specific job and company. Guidelines:
- Opening paragraph: express genuine enthusiasm for this specific role and company
- Middle paragraph: connect 2-3 specific accomplishments from the applicant's
  background to the key requirements of the role
- Closing paragraph: brief call to action, professional sign-off
- Be specific, not generic — reference the company name and role title explicitly
- Tone: professional but personable
- Length: 200-300 words

Respond with the cover letter text only — no subject line, no "Dear Hiring Manager"
boilerplate unless it feels natural. Do not add placeholders like [Your Name].
"""


class CoverLetterGenerator:
    def __init__(self, api_key: str) -> None:
        self.client = anthropic.Anthropic(api_key=api_key)

    async def generate(self, job: "JobListing", resume_summary: str) -> str:
        """Return cover letter text for the given job."""
        user_message = (
            f"COMPANY: {job.company}\n"
            f"ROLE: {job.title}\n"
            f"JOB DESCRIPTION:\n{job.description}\n\n"
            f"APPLICANT BACKGROUND SUMMARY:\n{resume_summary}\n\n"
            "Write the cover letter."
        )

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        return response.content[0].text.strip()
