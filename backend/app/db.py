"""SQLite snapshot of January 2026 wind actuals and forecast vintages."""

import os
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS actuals (
  start_time TEXT PRIMARY KEY,
  settlement_date TEXT NOT NULL,
  settlement_period INTEGER NOT NULL,
  generation_mw REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS forecasts (
  publish_time TEXT NOT NULL,
  start_time TEXT NOT NULL,
  settlement_date TEXT NOT NULL,
  settlement_period INTEGER NOT NULL,
  generation_mw REAL NOT NULL,
  PRIMARY KEY (publish_time, start_time)
);

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def default_db_path() -> Path:
    override = os.environ.get("DATA_PATH")
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "data" / "wind.sqlite",
        here.parents[1] / "data" / "wind.sqlite",
        Path.cwd() / "data" / "wind.sqlite",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def replace_snapshot(conn: sqlite3.Connection, actuals: list[dict], forecasts: list[dict], meta: dict[str, str]) -> None:
    with conn:
        conn.execute("DELETE FROM actuals")
        conn.execute("DELETE FROM forecasts")
        conn.execute("DELETE FROM meta")
        conn.executemany(
            """
            INSERT INTO actuals (start_time, settlement_date, settlement_period, generation_mw)
            VALUES (:start_time, :settlement_date, :settlement_period, :generation_mw)
            """,
            actuals,
        )
        conn.executemany(
            """
            INSERT INTO forecasts (
              publish_time, start_time, settlement_date, settlement_period, generation_mw
            ) VALUES (
              :publish_time, :start_time, :settlement_date, :settlement_period, :generation_mw
            )
            """,
            forecasts,
        )
        conn.executemany(
            "INSERT INTO meta (key, value) VALUES (:key, :value)",
            [{"key": key, "value": value} for key, value in meta.items()],
        )


def load_actuals(conn: sqlite3.Connection) -> dict[str, float]:
    return {row["start_time"]: row["generation_mw"] for row in conn.execute("SELECT start_time, generation_mw FROM actuals")}


def load_forecasts(conn: sqlite3.Connection) -> dict[str, dict[str, float]]:
    forecasts: dict[str, dict[str, float]] = {}
    for row in conn.execute("SELECT publish_time, start_time, generation_mw FROM forecasts"):
        forecasts.setdefault(row["publish_time"], {})[row["start_time"]] = row["generation_mw"]
    return forecasts
