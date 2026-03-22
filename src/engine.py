"""
ApplicationEngine: orchestrates the full job search → apply pipeline.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable, Type

from rich.console import Console
from rich.table import Table

from src.ai.cover_letter import CoverLetterGenerator
from src.ai.pdf_builder import PDFBuilder
from src.ai.resume_generator import ResumeGenerator
from src.browser.browser_manager import BrowserManager
from src.config import UserPreferences
from src.database.repository import JobRepository
from src.database.schema import init_db
from src.job_boards.base import JobBoard, JobListing
from src.job_boards.glassdoor import Glassdoor
from src.job_boards.indeed import Indeed
from src.job_boards.linkedin import LinkedIn
from src.memory.qa_memory import QAMemory

console = Console()

BOARD_MAP: dict[str, Type[JobBoard]] = {
    "linkedin": LinkedIn,
    "indeed": Indeed,
    "glassdoor": Glassdoor,
}


class _UIWriter:
    """Thin file-like wrapper that forwards Rich output to a log_fn callback."""

    def __init__(self, log_fn: Callable[[str], None]) -> None:
        self._fn = log_fn

    def write(self, text: str) -> None:
        if text.strip():
            self._fn(text)

    def flush(self) -> None:
        pass


class ApplicationEngine:
    def __init__(
        self,
        prefs: UserPreferences,
        dry_run: bool = False,
        limit: int | None = None,
        boards: list[str] | None = None,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        self.prefs = prefs
        self.dry_run = dry_run
        self.limit = limit or prefs.max_applications_per_run
        self.boards = boards or prefs.boards

        # When a log_fn is provided (UI mode), send Rich output there instead of stdout.
        if log_fn is not None:
            self._console = Console(
                file=_UIWriter(log_fn),
                markup=False,
                highlight=False,
                no_color=True,
            )
        else:
            self._console = console

        self.repo = JobRepository(prefs.db_path)
        self.qa_memory = QAMemory(prefs.db_path, ui_mode=log_fn is not None)
        self.resume_gen = ResumeGenerator(prefs.anthropic_api_key, prefs.resume_path)
        self.cl_gen = CoverLetterGenerator(prefs.anthropic_api_key)
        self.pdf_builder = PDFBuilder(prefs.generated_dir)

    async def run(self) -> None:
        # Ensure DB and directories exist
        prefs = self.prefs
        prefs.db_path.parent.mkdir(parents=True, exist_ok=True)
        prefs.generated_dir.mkdir(parents=True, exist_ok=True)
        prefs.session_path.mkdir(parents=True, exist_ok=True)
        await init_db(str(prefs.db_path))

        applied_count = 0

        async with BrowserManager(
            headless=prefs.headless,
            session_path=prefs.session_path / "browser_state.json",
        ) as browser:
            for board_name in self.boards:
                if applied_count >= self.limit:
                    break

                board_cls = BOARD_MAP.get(board_name)
                if not board_cls:
                    self._console.print(f"[red]Unknown board: {board_name}[/red]")
                    continue

                page = await browser.new_page()
                board = board_cls(
                    page=page,
                    prefs=prefs,
                    repo=self.repo,
                    qa_memory=self.qa_memory,
                    dry_run=self.dry_run,
                )

                self._console.rule(f"[bold blue]{board_name.title()}[/bold blue]")

                # Login
                try:
                    await board.login()
                except Exception as e:
                    self._console.print(f"[red]Login failed for {board_name}: {e}[/red]")
                    continue

                # Search
                self._console.print(f"Searching {board_name} for: {', '.join(prefs.job_titles)}")
                try:
                    jobs = await board.search()
                except Exception as e:
                    self._console.print(f"[red]Search failed for {board_name}: {e}[/red]")
                    continue

                self._console.print(f"Found [bold]{len(jobs)}[/bold] listings on {board_name}.")

                for job in jobs:
                    if applied_count >= self.limit:
                        break

                    # Save job to DB (no-op if already present)
                    await self.repo.upsert_job(job)

                    # Skip if already applied
                    if await self.repo.already_applied(job.url):
                        self._console.print(f"[dim]Skipping (already applied): {job.title} @ {job.company}[/dim]")
                        continue

                    self._console.print(f"\n[bold]Applying:[/bold] {job.title} @ {job.company} [{board_name}]")

                    # Generate tailored resume
                    try:
                        resume_dict = await self.resume_gen.generate(job)
                    except Exception as e:
                        self._console.print(f"[red]Resume generation failed: {e}[/red]")
                        await self.repo.mark_skipped(job.url, f"resume_gen_error:{e}")
                        continue

                    # Generate cover letter
                    try:
                        cl_text = await self.cl_gen.generate(job, resume_dict.get("summary", ""))
                    except Exception as e:
                        self._console.print(f"[yellow]Cover letter generation failed: {e} — continuing without.[/yellow]")
                        cl_text = ""

                    # Build PDFs
                    job_key = PDFBuilder.job_key(job.company, job.title)
                    try:
                        resume_pdf = self.pdf_builder.build_resume(resume_dict, job_key)
                        cl_pdf, _ = self.pdf_builder.build_cover_letter(
                            cl_text, job_key, resume_dict.get("personal", {}).get("name", "")
                        )
                    except Exception as e:
                        self._console.print(f"[red]PDF build failed: {e}[/red]")
                        await self.repo.mark_skipped(job.url, f"pdf_error:{e}")
                        continue

                    # Apply
                    try:
                        result = await board.apply(job, str(resume_pdf), str(cl_pdf))
                    except Exception as e:
                        result_cls = __import__("src.job_boards.base", fromlist=["ApplyResult"]).ApplyResult
                        result = result_cls(success=False, job_url=job.url, notes=str(e))

                    await self.repo.record_result(job, result)

                    if result.success:
                        applied_count += 1
                        self._console.print(f"[green]Applied! ({applied_count}/{self.limit})[/green]")
                    else:
                        self._console.print(f"[red]Failed: {result.notes}[/red]")

                    # Human-like delay between applications
                    if not self.dry_run and applied_count < self.limit:
                        delay = prefs.delay_between_applications_seconds
                        self._console.print(f"[dim]Waiting {delay}s before next application...[/dim]")
                        await asyncio.sleep(delay)

                await page.close()

        self._print_summary(applied_count)

    def _print_summary(self, applied_count: int) -> None:
        self._console.rule("[bold]Run Complete[/bold]")
        self._console.print(f"Applications submitted: [bold green]{applied_count}[/bold green]")
        if self.dry_run:
            self._console.print("[yellow]DRY RUN — no actual submissions were made.[/yellow]")
