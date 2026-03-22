#!/usr/bin/env python3
"""
Job Application Agent — CLI entry point.

Usage examples:
  python main.py run
  python main.py run --dry-run --limit 5 --boards linkedin indeed
  python main.py run --headless --limit 10
  python main.py status
  python main.py memory list
  python main.py setup
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()
ROOT = Path(__file__).parent


@click.group()
def cli():
    """Job Application Automation Agent."""


@cli.command()
@click.option("--dry-run", is_flag=True, help="Search and generate docs but do not submit.")
@click.option("--headless", is_flag=True, default=None, help="Run browser in headless mode.")
@click.option("--limit", type=int, default=None, help="Max applications for this run.")
@click.option(
    "--boards",
    multiple=True,
    type=click.Choice(["linkedin", "indeed", "glassdoor"]),
    help="Which job boards to target (default: all from config).",
)
@click.option("--config", type=click.Path(), default=None, help="Path to config.json.")
def run(dry_run: bool, headless: bool | None, limit: int | None, boards: tuple, config: str | None):
    """Search for jobs and apply automatically."""
    from src.config import load_config
    from src.engine import ApplicationEngine

    cfg_path = Path(config) if config else None
    prefs = load_config(cfg_path)

    if not prefs.anthropic_api_key:
        console.print("[red]ANTHROPIC_API_KEY is not set. Add it to your .env file.[/red]")
        sys.exit(1)

    if not prefs.resume_path.exists():
        console.print(
            f"[red]Base resume not found at {prefs.resume_path}.[/red]\n"
            "Run [bold]python main.py setup[/bold] to create it."
        )
        sys.exit(1)

    if headless is not None:
        prefs.headless = headless

    engine = ApplicationEngine(
        prefs=prefs,
        dry_run=dry_run,
        limit=limit,
        boards=list(boards) if boards else None,
    )

    if dry_run:
        console.print("[yellow]DRY RUN mode — no applications will be submitted.[/yellow]")

    asyncio.run(engine.run())


@cli.command()
@click.option("--config", type=click.Path(), default=None)
def status(config: str | None):
    """Show a summary of all tracked job applications."""
    from src.config import load_config
    from src.database.repository import JobRepository

    prefs = load_config(Path(config) if config else None)
    repo = JobRepository(prefs.db_path)

    async def _show():
        jobs = await repo.get_all_jobs()
        if not jobs:
            console.print("No jobs tracked yet.")
            return

        table = Table(title="Job Applications", show_lines=True)
        table.add_column("Status", style="bold")
        table.add_column("Title")
        table.add_column("Company")
        table.add_column("Board")
        table.add_column("Applied At")

        status_colors = {
            "applied": "green",
            "failed": "red",
            "skipped": "yellow",
            "found": "cyan",
        }
        for j in jobs:
            color = status_colors.get(j["status"], "white")
            table.add_row(
                f"[{color}]{j['status']}[/{color}]",
                j["title"],
                j["company"],
                j["board"],
                j.get("applied_at") or "—",
            )

        console.print(table)
        counts = {}
        for j in jobs:
            counts[j["status"]] = counts.get(j["status"], 0) + 1
        console.print(
            f"Total: {len(jobs)} | "
            + " | ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        )

    asyncio.run(_show())


@cli.group()
def memory():
    """Manage the Q&A memory store."""


@memory.command("list")
@click.option("--config", type=click.Path(), default=None)
def memory_list(config: str | None):
    """List all stored Q&A pairs."""
    from src.config import load_config
    from src.memory.qa_memory import QAMemory

    prefs = load_config(Path(config) if config else None)
    qa = QAMemory(prefs.db_path)

    async def _list():
        entries = await qa.list_all()
        if not entries:
            console.print("No Q&A entries stored yet.")
            return
        table = Table(title="Q&A Memory", show_lines=True)
        table.add_column("Question", max_width=60)
        table.add_column("Answer", max_width=40)
        table.add_column("Uses", justify="right")
        for e in entries:
            table.add_row(e["question_text"][:60], e["answer"][:40], str(e["use_count"]))
        console.print(table)

    asyncio.run(_list())


@memory.command("clear")
@click.option("--config", type=click.Path(), default=None)
@click.confirmation_option(prompt="This will delete all stored Q&A answers. Are you sure?")
def memory_clear(config: str | None):
    """Delete all stored Q&A answers."""
    from src.config import load_config
    import aiosqlite

    prefs = load_config(Path(config) if config else None)

    async def _clear():
        async with aiosqlite.connect(str(prefs.db_path)) as db:
            await db.execute("DELETE FROM qa_memory")
            await db.commit()
        console.print("[green]Q&A memory cleared.[/green]")

    asyncio.run(_clear())


@cli.command()
def setup():
    """Interactive setup: create base_resume.json and config.json."""
    console.print("[bold]Job Agent Setup[/bold]")

    # Config
    cfg_path = ROOT / "config.json"
    if cfg_path.exists():
        console.print(f"[yellow]config.json already exists at {cfg_path}[/yellow]")
    else:
        titles = click.prompt("Job titles (comma-separated)", default="Software Engineer")
        location = click.prompt("Location", default="Remote")
        salary = click.prompt("Minimum salary", default="100000")
        cfg = {
            "job_titles": [t.strip() for t in titles.split(",")],
            "location": location,
            "salary_min": int(salary),
            "experience_years": 5,
            "skills": [],
            "blacklisted_companies": [],
            "max_applications_per_run": 20,
            "headless": False,
            "boards": ["linkedin", "indeed", "glassdoor"],
            "delay_between_applications_seconds": 45,
            "session_dir": "data/sessions",
            "credentials": {
                "linkedin": {"email": "", "password": ""},
                "indeed": {"email": "", "password": ""},
                "glassdoor": {"email": "", "password": ""},
            },
        }
        cfg_path.write_text(json.dumps(cfg, indent=2))
        console.print(f"[green]Created {cfg_path}[/green]")

    # Resume
    resume_path = ROOT / "data" / "base_resume.json"
    if resume_path.exists():
        console.print(f"[yellow]base_resume.json already exists at {resume_path}[/yellow]")
    else:
        resume_path.parent.mkdir(parents=True, exist_ok=True)
        template = {
            "personal": {
                "name": click.prompt("Full name"),
                "email": click.prompt("Email"),
                "phone": click.prompt("Phone"),
                "linkedin": click.prompt("LinkedIn URL", default=""),
                "github": click.prompt("GitHub URL", default=""),
            },
            "summary": click.prompt("Professional summary (1-3 sentences)"),
            "experience": [],
            "education": [],
            "skills": [],
            "certifications": [],
        }
        resume_path.write_text(json.dumps(template, indent=2))
        console.print(f"[green]Created {resume_path}[/green]")
        console.print(
            "[dim]Edit data/base_resume.json to add your experience, education, and skills.[/dim]"
        )

    # .env
    env_path = ROOT / ".env"
    if not env_path.exists():
        api_key = click.prompt("Anthropic API key (leave blank to set later)", default="")
        env_path.write_text(f"ANTHROPIC_API_KEY={api_key}\n")
        console.print(f"[green]Created .env[/green]")

    console.print("\n[bold green]Setup complete![/bold green]")
    console.print("Next: fill in your credentials in config.json, then run [bold]python main.py run --dry-run[/bold]")


if __name__ == "__main__":
    cli()
