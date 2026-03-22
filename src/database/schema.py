"""
SQLite schema definitions and initialization.
"""
import aiosqlite

JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    title             TEXT NOT NULL,
    company           TEXT NOT NULL,
    board             TEXT NOT NULL,
    job_url           TEXT UNIQUE NOT NULL,
    external_url      TEXT,
    description       TEXT,
    status            TEXT NOT NULL DEFAULT 'found',
    applied_at        DATETIME,
    resume_path       TEXT,
    cover_letter_path TEXT,
    notes             TEXT,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

QA_MEMORY_TABLE = """
CREATE TABLE IF NOT EXISTS qa_memory (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    question_hash TEXT UNIQUE NOT NULL,
    question_text TEXT NOT NULL,
    answer        TEXT NOT NULL,
    input_type    TEXT NOT NULL DEFAULT 'text',
    use_count     INTEGER DEFAULT 1,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


async def init_db(db_path: str) -> None:
    """Create tables if they do not exist."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(JOBS_TABLE)
        await db.execute(QA_MEMORY_TABLE)
        await db.commit()
