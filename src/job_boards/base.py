"""
Abstract base classes for job boards and shared data models.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

    from src.config import UserPreferences
    from src.database.repository import JobRepository
    from src.memory.qa_memory import QAMemory


@dataclass
class JobListing:
    title: str
    company: str
    board: str
    url: str
    description: str = ""
    external_url: str | None = None
    requires_cover_letter: bool = False
    salary: str = ""
    location: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class ApplyResult:
    success: bool
    job_url: str
    resume_path: str = ""
    cover_letter_path: str = ""
    notes: str = ""


class JobBoard(ABC):
    """
    Abstract base for all job board implementations.
    Subclasses implement login, search, and apply.
    """

    def __init__(
        self,
        page: "Page",
        prefs: "UserPreferences",
        repo: "JobRepository",
        qa_memory: "QAMemory",
        dry_run: bool = False,
    ) -> None:
        self.page = page
        self.prefs = prefs
        self.repo = repo
        self.qa_memory = qa_memory
        self.dry_run = dry_run

    @abstractmethod
    async def login(self) -> None:
        """Log in to the job board."""

    @abstractmethod
    async def search(self) -> list[JobListing]:
        """
        Search for jobs matching user preferences.
        Returns a list of JobListing objects.
        """

    @abstractmethod
    async def apply(
        self,
        job: JobListing,
        resume_path: str,
        cover_letter_path: str,
    ) -> ApplyResult:
        """
        Fill and submit a job application.
        Must handle external redirects to company websites.
        Returns ApplyResult indicating success or failure.
        """

    async def _answer_form_question(self, question: str, input_type: str = "text") -> str:
        """
        Look up question in QA memory; prompt user if unknown.
        """
        return await self.qa_memory.get_or_ask(question, input_type)
