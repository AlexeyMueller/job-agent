import sqlite3
from datetime import UTC, datetime

from job_agent.models import Job
from job_agent.scorer import ScoreResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    source TEXT NOT NULL,
    ref TEXT NOT NULL,
    title TEXT,
    employer TEXT,
    location TEXT,
    url TEXT,
    published TEXT,
    home_office INTEGER,
    distance_km INTEGER,
    work_mode TEXT,
    model_score INTEGER,
    final_score INTEGER,
    apply INTEGER,
    summary TEXT,
    result_json TEXT,
    scored_at TEXT,
    PRIMARY KEY (source, ref)
)
"""


class Tracker:
    """SQLite store of scored vacancies. Prevents paying twice for the same vacancy."""

    def __init__(self, path: str = "jobs.db") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(SCHEMA)
        self._conn.commit()

    def has(self, source: str, ref: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM jobs WHERE source = ? AND ref = ?", (source, ref)
        ).fetchone()
        return row is not None

    def save(self, job: Job, result: ScoreResult, final_score: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                job.source,
                job.ref,
                job.title,
                job.employer,
                job.location,
                job.url,
                job.published.isoformat() if job.published else None,
                None if job.home_office is None else int(job.home_office),
                job.distance_km,
                result.work_mode,
                result.score,
                final_score,
                int(result.apply),
                result.summary,
                result.model_dump_json(),
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )
        self._conn.commit()

    def top(self, min_score: int = 0, limit: int = 50) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM jobs WHERE final_score >= ? "
            "ORDER BY final_score DESC, published DESC LIMIT ?",
            (min_score, limit),
        ).fetchall()

    def close(self) -> None:
        self._conn.close()
