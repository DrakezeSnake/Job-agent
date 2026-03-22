"""
Async database access layer for jobs and Q&A memory.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

import aiosqlite


# Use TYPE_CHECKING to avoid circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.job_boards.base import ApplyResult, JobListing


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _hash(text: str) -> str:
    return hashlib.sha256(_normalize(text).encode()).hexdigest()


class JobRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)

    async def already_applied(self, job_url: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT status FROM jobs WHERE job_url = ?", (job_url,)
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0] == "applied":
                    return True
        return False

    async def upsert_job(self, job: JobListing) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO jobs (title, company, board, job_url, external_url, description, status)
                VALUES (?, ?, ?, ?, ?, ?, 'found')
                ON CONFLICT(job_url) DO NOTHING
                """,
                (job.title, job.company, job.board, job.url, job.external_url, job.description),
            )
            await db.commit()

    async def record_result(self, job: JobListing, result: ApplyResult) -> None:
        status = "applied" if result.success else "failed"
        applied_at = datetime.utcnow().isoformat() if result.success else None
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE jobs
                SET status = ?, applied_at = ?, resume_path = ?,
                    cover_letter_path = ?, notes = ?
                WHERE job_url = ?
                """,
                (
                    status,
                    applied_at,
                    result.resume_path,
                    result.cover_letter_path,
                    result.notes,
                    job.url,
                ),
            )
            await db.commit()

    async def mark_skipped(self, job_url: str, reason: str = "") -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE jobs SET status = 'skipped', notes = ? WHERE job_url = ?",
                (reason, job_url),
            )
            await db.commit()

    async def get_all_jobs(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM jobs ORDER BY created_at DESC") as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]


class QAMemoryRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)

    async def find_exact(self, question: str) -> str | None:
        h = _hash(question)
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT answer FROM qa_memory WHERE question_hash = ?", (h,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    await db.execute(
                        "UPDATE qa_memory SET use_count = use_count + 1 WHERE question_hash = ?",
                        (h,),
                    )
                    await db.commit()
                    return row[0]
        return None

    async def get_all(self) -> list[tuple[str, str]]:
        """Return list of (normalized_question, answer) for fuzzy matching."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT question_text, answer FROM qa_memory") as cursor:
                return [(row[0], row[1]) for row in await cursor.fetchall()]

    async def store(self, question: str, answer: str, input_type: str = "text") -> None:
        h = _hash(question)
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO qa_memory (question_hash, question_text, answer, input_type, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(question_hash) DO UPDATE SET
                    answer = excluded.answer,
                    use_count = use_count + 1,
                    updated_at = excluded.updated_at
                """,
                (h, question, answer, input_type, now, now),
            )
            await db.commit()
