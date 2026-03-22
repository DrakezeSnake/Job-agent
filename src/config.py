"""
Loads user preferences from config.json and .env.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

ROOT = Path(__file__).parent.parent


class Credentials(BaseModel):
    email: str = ""
    password: str = ""


class BoardCredentials(BaseModel):
    linkedin: Credentials = Field(default_factory=Credentials)
    indeed: Credentials = Field(default_factory=Credentials)
    glassdoor: Credentials = Field(default_factory=Credentials)


class GoogleCredentials(BaseModel):
    email: str = ""
    password: str = ""


class UserPreferences(BaseModel):
    job_titles: list[str] = Field(default_factory=list)
    location: str = "Remote"
    salary_min: int = 0
    experience_years: int = 0
    skills: list[str] = Field(default_factory=list)
    blacklisted_companies: list[str] = Field(default_factory=list)
    max_applications_per_run: int = 20
    headless: bool = False
    boards: list[str] = Field(default_factory=lambda: ["linkedin", "indeed", "glassdoor"])
    delay_between_applications_seconds: int = 45
    session_dir: str = "data/sessions"
    credentials: BoardCredentials = Field(default_factory=BoardCredentials)
    use_google_login: bool = False
    google_credentials: GoogleCredentials = Field(default_factory=GoogleCredentials)

    # Loaded from environment
    anthropic_api_key: str = ""

    def get_credentials(self, board: str) -> Credentials:
        return getattr(self.credentials, board, Credentials())

    @property
    def db_path(self) -> Path:
        return ROOT / "data" / "jobs.db"

    @property
    def resume_path(self) -> Path:
        return ROOT / "data" / "base_resume.json"

    @property
    def generated_dir(self) -> Path:
        return ROOT / "data" / "generated"

    @property
    def session_path(self) -> Path:
        return ROOT / self.session_dir


def load_config(config_path: Path | None = None) -> UserPreferences:
    path = config_path or ROOT / "config.json"
    raw: dict = {}
    if path.exists():
        with open(path) as f:
            raw = json.load(f)

    # Env overrides for credentials
    for board in ("linkedin", "indeed", "glassdoor"):
        email_env = os.getenv(f"{board.upper()}_EMAIL")
        password_env = os.getenv(f"{board.upper()}_PASSWORD")
        if email_env:
            raw.setdefault("credentials", {}).setdefault(board, {})["email"] = email_env
        if password_env:
            raw.setdefault("credentials", {}).setdefault(board, {})["password"] = password_env

    prefs = UserPreferences(**raw)
    prefs.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
    return prefs
