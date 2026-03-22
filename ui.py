"""
Gradio web UI for the Job Application Agent.
Run with:  python ui.py
Then open  http://localhost:7860  in your browser.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import queue
import re
import threading
from pathlib import Path

import aiosqlite
import gradio as gr

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.json"
RESUME_PATH = ROOT / "data" / "base_resume.json"
DB_PATH = ROOT / "data" / "jobs.db"

# ── Helpers ─────────────────────────────────────────────────────────────────


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _list_to_str(lst: list) -> str:
    return ", ".join(str(x) for x in lst)


def _str_to_list(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


# ── Run tab ─────────────────────────────────────────────────────────────────


def run_agent(selected_boards: list[str], dry_run: bool, headless: bool, limit: int):
    """Generator: streams live log output from the engine to the UI."""
    if not selected_boards:
        yield "Please select at least one job board."
        return

    log_q: queue.Queue[str | None] = queue.Queue()

    def log_fn(text: str) -> None:
        # Strip any residual Rich markup tags before displaying
        clean = re.sub(r"\[/?[^\]]*\]", "", text).strip()
        if clean:
            log_q.put(clean)

    def thread_target() -> None:
        async def _run() -> None:
            from src.config import load_config
            from src.engine import ApplicationEngine

            try:
                prefs = load_config(CONFIG_PATH)
                prefs.headless = headless
                engine = ApplicationEngine(
                    prefs=prefs,
                    dry_run=dry_run,
                    limit=int(limit),
                    boards=list(selected_boards),
                    log_fn=log_fn,
                )
                await engine.run()
            except Exception as exc:
                log_fn(f"ERROR: {exc}")
            finally:
                log_q.put(None)  # sentinel — run is done

        asyncio.run(_run())

    t = threading.Thread(target=thread_target, daemon=True)
    t.start()

    lines: list[str] = []
    while True:
        try:
            msg = log_q.get(timeout=0.4)
            if msg is None:
                break
            lines.append(msg)
            yield "\n".join(lines)
        except queue.Empty:
            if not t.is_alive():
                break
            yield "\n".join(lines)

    lines.append("─── Run complete ───")
    yield "\n".join(lines)


# ── Settings tab ─────────────────────────────────────────────────────────────


def settings_load():
    cfg = _load_json(CONFIG_PATH)
    creds = cfg.get("credentials", {})
    return (
        _list_to_str(cfg.get("job_titles", [])),
        cfg.get("location", "Remote"),
        cfg.get("salary_min", 0),
        cfg.get("experience_years", 5),
        _list_to_str(cfg.get("skills", [])),
        _list_to_str(cfg.get("blacklisted_companies", [])),
        cfg.get("max_applications_per_run", 20),
        cfg.get("delay_between_applications_seconds", 45),
        creds.get("linkedin", {}).get("email", ""),
        creds.get("linkedin", {}).get("password", ""),
        creds.get("indeed", {}).get("email", ""),
        creds.get("indeed", {}).get("password", ""),
        creds.get("glassdoor", {}).get("email", ""),
        creds.get("glassdoor", {}).get("password", ""),
    )


def settings_save(
    job_titles, location, salary_min, experience_years, skills, blacklisted,
    max_apps, delay,
    li_email, li_pass, in_email, in_pass, gl_email, gl_pass,
):
    cfg = _load_json(CONFIG_PATH)
    cfg["job_titles"] = _str_to_list(job_titles)
    cfg["location"] = location
    cfg["salary_min"] = int(salary_min or 0)
    cfg["experience_years"] = int(experience_years or 0)
    cfg["skills"] = _str_to_list(skills)
    cfg["blacklisted_companies"] = _str_to_list(blacklisted)
    cfg["max_applications_per_run"] = int(max_apps or 20)
    cfg["delay_between_applications_seconds"] = int(delay or 45)
    cfg.setdefault("credentials", {})
    cfg["credentials"].setdefault("linkedin", {})
    cfg["credentials"].setdefault("indeed", {})
    cfg["credentials"].setdefault("glassdoor", {})
    cfg["credentials"]["linkedin"]["email"] = li_email
    cfg["credentials"]["linkedin"]["password"] = li_pass
    cfg["credentials"]["indeed"]["email"] = in_email
    cfg["credentials"]["indeed"]["password"] = in_pass
    cfg["credentials"]["glassdoor"]["email"] = gl_email
    cfg["credentials"]["glassdoor"]["password"] = gl_pass
    _save_json(CONFIG_PATH, cfg)
    return "Settings saved!"


# ── Resume tab ───────────────────────────────────────────────────────────────


def resume_load():
    r = _load_json(RESUME_PATH)
    p = r.get("personal", {})
    return (
        p.get("name", ""),
        p.get("email", ""),
        p.get("phone", ""),
        p.get("linkedin", ""),
        r.get("summary", ""),
        _list_to_str(r.get("skills", [])),
        json.dumps(r.get("experience", []), indent=2, ensure_ascii=False),
        json.dumps(r.get("education", []), indent=2, ensure_ascii=False),
    )


def resume_save(name, email, phone, linkedin, summary, skills_str, experience_json, education_json):
    r = _load_json(RESUME_PATH)
    r["personal"]["name"] = name
    r["personal"]["email"] = email
    r["personal"]["phone"] = phone
    r["personal"]["linkedin"] = linkedin
    r["summary"] = summary
    r["skills"] = _str_to_list(skills_str)
    try:
        r["experience"] = json.loads(experience_json)
    except json.JSONDecodeError as exc:
        return f"Experience JSON error: {exc}"
    try:
        r["education"] = json.loads(education_json)
    except json.JSONDecodeError as exc:
        return f"Education JSON error: {exc}"
    _save_json(RESUME_PATH, r)
    return "Resume saved!"


# ── Applications tab ─────────────────────────────────────────────────────────


def apps_load():
    async def _fetch():
        if not DB_PATH.exists():
            return []
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT title, company, board, status, applied_at, job_url "
                "FROM jobs ORDER BY created_at DESC"
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    rows = asyncio.run(_fetch())
    if not rows:
        return [], "No applications tracked yet."

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    summary = "  |  ".join(f"{k}: {v}" for k, v in counts.items())

    data = [
        [r["title"], r["company"], r["board"], r["status"], r["applied_at"] or "", r["job_url"]]
        for r in rows
    ]
    return data, summary


# ── Q&A Memory tab ───────────────────────────────────────────────────────────


def qa_load():
    async def _fetch():
        if not DB_PATH.exists():
            return []
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT question_text, answer, use_count FROM qa_memory ORDER BY use_count DESC"
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    rows = asyncio.run(_fetch())
    return [[r["question_text"], r["answer"], r["use_count"]] for r in rows]


def qa_add(question: str, answer: str):
    if not question.strip() or not answer.strip():
        return "Fill in both fields.", qa_load()

    async def _store():
        norm = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", question.lower())).strip()
        h = hashlib.sha256(norm.encode()).hexdigest()
        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute(
                """INSERT INTO qa_memory (question_hash, question_text, answer, input_type)
                   VALUES (?, ?, ?, 'text')
                   ON CONFLICT(question_hash) DO UPDATE
                   SET answer=excluded.answer, updated_at=CURRENT_TIMESTAMP""",
                (h, question.strip(), answer.strip()),
            )
            await db.commit()

    asyncio.run(_store())
    return "Answer saved!", qa_load()


def qa_clear():
    async def _clear():
        if not DB_PATH.exists():
            return
        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute("DELETE FROM qa_memory")
            await db.commit()

    asyncio.run(_clear())
    return qa_load()


# ── Build UI ─────────────────────────────────────────────────────────────────

with gr.Blocks(title="Job Agent") as demo:
    gr.Markdown("# Job Application Agent")
    gr.Markdown("Automated job search and application powered by Claude AI")

    with gr.Tabs():

        # ── Tab 1: Run ──────────────────────────────────────────────────────
        with gr.Tab("Run"):
            with gr.Row():
                with gr.Column(scale=1):
                    boards_cb = gr.CheckboxGroup(
                        choices=["linkedin", "indeed", "glassdoor"],
                        value=["linkedin"],
                        label="Job Boards",
                    )
                    dry_run_chk = gr.Checkbox(label="Dry Run (search only, no submissions)", value=False)
                    headless_chk = gr.Checkbox(label="Headless Browser (no visible window)", value=False)
                    limit_num = gr.Number(label="Max Applications", value=20, minimum=1, maximum=200, step=1)
                    start_btn = gr.Button("Start Agent", variant="primary", size="lg")
                with gr.Column(scale=2):
                    log_box = gr.Textbox(
                        label="Live Log",
                        lines=28,
                        max_lines=28,
                        autoscroll=True,
                        placeholder="Log output appears here when the agent runs...",
                    )

            start_btn.click(
                run_agent,
                inputs=[boards_cb, dry_run_chk, headless_chk, limit_num],
                outputs=[log_box],
            )

        # ── Tab 2: Settings ─────────────────────────────────────────────────
        with gr.Tab("Settings"):
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### Job Search Preferences")
                    s_titles = gr.Textbox(label="Job Titles (comma-separated)", lines=2)
                    s_location = gr.Textbox(label="Location")
                    s_salary = gr.Number(label="Minimum Salary (USD/year)")
                    s_exp = gr.Number(label="Years of Experience")
                    s_skills = gr.Textbox(label="Skills (comma-separated)", lines=3)
                    s_blacklist = gr.Textbox(label="Blacklisted Companies (comma-separated)", lines=2)
                    s_max_apps = gr.Number(label="Max Applications per Run")
                    s_delay = gr.Number(label="Delay Between Applications (seconds)")

                with gr.Column():
                    gr.Markdown("### Job Board Credentials")
                    gr.Markdown("**LinkedIn**")
                    s_li_email = gr.Textbox(label="Email")
                    s_li_pass = gr.Textbox(label="Password", type="password")
                    gr.Markdown("**Indeed**")
                    s_in_email = gr.Textbox(label="Email")
                    s_in_pass = gr.Textbox(label="Password", type="password")
                    gr.Markdown("**Glassdoor**")
                    s_gl_email = gr.Textbox(label="Email")
                    s_gl_pass = gr.Textbox(label="Password", type="password")

            save_btn = gr.Button("Save Settings", variant="primary")
            save_status = gr.Textbox(label="Status", interactive=False, max_lines=1)

            _settings_inputs = [
                s_titles, s_location, s_salary, s_exp, s_skills, s_blacklist,
                s_max_apps, s_delay,
                s_li_email, s_li_pass, s_in_email, s_in_pass, s_gl_email, s_gl_pass,
            ]
            _settings_outputs = [
                s_titles, s_location, s_salary, s_exp, s_skills, s_blacklist,
                s_max_apps, s_delay,
                s_li_email, s_li_pass, s_in_email, s_in_pass, s_gl_email, s_gl_pass,
            ]

            save_btn.click(settings_save, inputs=_settings_inputs, outputs=[save_status])
            demo.load(settings_load, outputs=_settings_outputs)

        # ── Tab 3: Resume ───────────────────────────────────────────────────
        with gr.Tab("Resume"):
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### Personal Info")
                    r_name = gr.Textbox(label="Full Name")
                    r_email = gr.Textbox(label="Email")
                    r_phone = gr.Textbox(label="Phone")
                    r_linkedin = gr.Textbox(label="LinkedIn URL")
                    gr.Markdown("### Summary")
                    r_summary = gr.Textbox(label="Professional Summary", lines=5)
                    gr.Markdown("### Skills")
                    r_skills = gr.Textbox(label="Skills (comma-separated)", lines=3)

                with gr.Column():
                    gr.Markdown("### Experience (JSON)")
                    r_experience = gr.Textbox(
                        label="Experience entries",
                        lines=20,
                        info="Edit raw JSON — each entry: {company, title, start, end, bullets:[]}",
                    )
                    gr.Markdown("### Education (JSON)")
                    r_education = gr.Textbox(
                        label="Education entries",
                        lines=8,
                        info="Edit raw JSON — each entry: {school, degree, year}",
                    )

            r_save_btn = gr.Button("Save Resume", variant="primary")
            r_save_status = gr.Textbox(label="Status", interactive=False, max_lines=1)

            _resume_inputs = [r_name, r_email, r_phone, r_linkedin, r_summary, r_skills, r_experience, r_education]
            _resume_outputs = [r_name, r_email, r_phone, r_linkedin, r_summary, r_skills, r_experience, r_education]

            r_save_btn.click(resume_save, inputs=_resume_inputs, outputs=[r_save_status])
            demo.load(resume_load, outputs=_resume_outputs)

        # ── Tab 4: Applications ─────────────────────────────────────────────
        with gr.Tab("Applications"):
            apps_summary = gr.Textbox(label="Summary", interactive=False, max_lines=1)
            apps_table = gr.Dataframe(
                headers=["Title", "Company", "Board", "Status", "Applied At", "URL"],
                label="All Applications",
                wrap=True,
                interactive=False,
            )
            apps_refresh_btn = gr.Button("Refresh")
            apps_refresh_btn.click(apps_load, outputs=[apps_table, apps_summary])
            demo.load(apps_load, outputs=[apps_table, apps_summary])

        # ── Tab 5: Q&A Memory ───────────────────────────────────────────────
        with gr.Tab("Q&A Memory"):
            gr.Markdown(
                "Pre-store answers to common application questions. "
                "The agent uses these automatically — no terminal interaction needed."
            )
            qa_table = gr.Dataframe(
                headers=["Question", "Answer", "Times Used"],
                label="Stored Answers",
                wrap=True,
                interactive=False,
            )
            with gr.Row():
                qa_q_in = gr.Textbox(
                    label="Question",
                    placeholder="e.g. Are you authorized to work in the US?",
                    scale=2,
                )
                qa_a_in = gr.Textbox(label="Answer", placeholder="e.g. Yes", scale=1)
            with gr.Row():
                qa_add_btn = gr.Button("Add / Update Answer", variant="primary")
                qa_clear_btn = gr.Button("Clear All Memory", variant="stop")
            qa_status = gr.Textbox(label="Status", interactive=False, max_lines=1)

            qa_add_btn.click(qa_add, inputs=[qa_q_in, qa_a_in], outputs=[qa_status, qa_table])
            qa_clear_btn.click(qa_clear, outputs=[qa_table])
            demo.load(qa_load, outputs=[qa_table])


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, inbrowser=True, theme=gr.themes.Soft())
