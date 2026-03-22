"""
Tailors the base resume JSON to a specific job using the Claude API.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import anthropic

if TYPE_CHECKING:
    from src.job_boards.base import JobListing

SYSTEM_PROMPT = """\
You are an expert resume writer and ATS optimization specialist.
Given a base resume in JSON format and a job description, produce a tailored
version of the resume that:
- Highlights the most relevant experience and skills for this specific role
- Incorporates keywords from the job description naturally
- Reorders bullet points to lead with the most relevant achievements
- Adjusts the professional summary to match the role and company
- Does NOT invent experience or qualifications that are not in the base resume

Respond ONLY with valid JSON using the exact same schema as the input resume.
Do not include any explanation or markdown — just the JSON object.
"""


class ResumeGenerator:
    def __init__(self, api_key: str, base_resume_path: Path) -> None:
        self.client = anthropic.Anthropic(api_key=api_key)
        self.base_resume_path = base_resume_path
        self._base_resume: dict | None = None

    def _load_base_resume(self) -> dict:
        if self._base_resume is None:
            with open(self.base_resume_path) as f:
                self._base_resume = json.load(f)
        return self._base_resume

    async def generate(self, job: "JobListing") -> dict:
        """Return a tailored resume dict for the given job."""
        base = self._load_base_resume()
        user_message = (
            f"BASE RESUME:\n{json.dumps(base, indent=2)}\n\n"
            f"JOB TITLE: {job.title}\n"
            f"COMPANY: {job.company}\n"
            f"JOB DESCRIPTION:\n{job.description}\n\n"
            "Return the tailored resume JSON."
        )

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        raw = response.content[0].text.strip()
        # Strip potential markdown code fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
