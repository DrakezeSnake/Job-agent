"""
Q&A memory: looks up previously answered application questions,
prompts the user for new ones, and stores them for reuse.

Matching strategy:
  1. Exact SHA256 match on normalized question text
  2. Fuzzy match (rapidfuzz) with similarity >= 0.85
  3. If no match: prompt user interactively, store answer
"""
from __future__ import annotations

import re
from pathlib import Path

from rapidfuzz import fuzz
from rich.console import Console
from rich.prompt import Prompt

from src.database.repository import QAMemoryRepository

console = Console()

FUZZY_THRESHOLD = 85  # rapidfuzz returns 0-100


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


class QAMemory:
    def __init__(self, db_path: str | Path, ui_mode: bool = False) -> None:
        self._repo = QAMemoryRepository(db_path)
        self._ui_mode = ui_mode

    async def find_answer(self, question: str) -> tuple[str, str] | None:
        """
        Returns (answer, match_type) or None.
        match_type is 'exact' or 'fuzzy'.
        """
        # 1. Exact match
        answer = await self._repo.find_exact(question)
        if answer is not None:
            return answer, "exact"

        # 2. Fuzzy match
        all_entries = await self._repo.get_all()
        norm_q = _normalize(question)
        best_score = 0
        best_answer = None
        for stored_q, stored_a in all_entries:
            score = fuzz.token_set_ratio(norm_q, _normalize(stored_q))
            if score > best_score:
                best_score = score
                best_answer = stored_a

        if best_score >= FUZZY_THRESHOLD and best_answer is not None:
            return best_answer, "fuzzy"

        return None

    async def ask_user_and_store(self, question: str, input_type: str = "text") -> str:
        """Prompt the user interactively, store the answer, and return it.

        In UI mode, the question cannot be answered interactively — log a warning
        and return an empty string so the calling code can handle it gracefully.
        """
        if self._ui_mode:
            console.print(
                f"[yellow]UI mode: unanswered question (add it in Q&A Memory tab): {question[:80]}[/yellow]"
            )
            return ""

        console.print(f"\n[bold yellow]New application question:[/bold yellow]")
        console.print(f"[cyan]{question}[/cyan]")
        if input_type == "radio":
            console.print("[dim]  (radio/select — type the option value or label)[/dim]")

        answer = Prompt.ask("[bold]Your answer[/bold]")
        await self._repo.store(question, answer, input_type)
        console.print("[green]Answer saved to memory.[/green]\n")
        return answer

    async def get_or_ask(self, question: str, input_type: str = "text") -> str:
        """
        Main entry point: returns a stored answer or prompts the user.
        """
        result = await self.find_answer(question)
        if result:
            answer, match_type = result
            icon = "exact match" if match_type == "exact" else f"fuzzy match"
            console.print(
                f"[dim]QA memory ({icon}): '{question[:60]}' → '{answer[:60]}'[/dim]"
            )
            return answer

        return await self.ask_user_and_store(question, input_type)

    async def list_all(self) -> list[dict]:
        """Return all stored Q&A pairs for inspection."""
        async with __import__("aiosqlite").connect(str(self._repo.db_path)) as db:
            db.row_factory = __import__("aiosqlite").Row
            async with db.execute(
                "SELECT question_text, answer, use_count, created_at FROM qa_memory ORDER BY use_count DESC"
            ) as cursor:
                return [dict(r) for r in await cursor.fetchall()]
