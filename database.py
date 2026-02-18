import sqlite3
import os
from datetime import datetime, date
from typing import Optional, List, Dict


DB_PATH = os.environ.get("DB_PATH", "jobs.db")


class Database:
    def __init__(self):
        self.db_path = DB_PATH

    def get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        conn = self.get_conn()
        cursor = conn.cursor()

        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                name        TEXT,
                subscribed  INTEGER DEFAULT 1,
                filters     TEXT DEFAULT 'Lahat',
                joined_at   TEXT DEFAULT (datetime('now', '+8 hours'))
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                company     TEXT,
                link        TEXT UNIQUE NOT NULL,
                category    TEXT,
                location    TEXT DEFAULT 'Philippines',
                source      TEXT,
                date_found  TEXT DEFAULT (datetime('now', '+8 hours'))
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_date ON jobs(date_found);
            CREATE INDEX IF NOT EXISTS idx_users_subscribed ON users(subscribed);
        """)
        conn.commit()
        conn.close()

    # ── USERS ──────────────────────────────────────

    def add_user(self, user_id: int, name: str):
        conn = self.get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, name) VALUES (?, ?)",
            (user_id, name),
        )
        conn.commit()
        conn.close()

    def get_user(self, user_id: int) -> Optional[Dict]:
        conn = self.get_conn()
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def subscribe_user(self, user_id: int):
        conn = self.get_conn()
        conn.execute("UPDATE users SET subscribed = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    def unsubscribe_user(self, user_id: int):
        conn = self.get_conn()
        conn.execute("UPDATE users SET subscribed = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    def set_filter(self, user_id: int, filter_value: str):
        conn = self.get_conn()
        conn.execute("UPDATE users SET filters = ? WHERE user_id = ?", (filter_value, user_id))
        conn.commit()
        conn.close()

    def get_subscribers(self) -> List[Dict]:
        conn = self.get_conn()
        rows = conn.execute("SELECT * FROM users WHERE subscribed = 1").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def count_users(self) -> int:
        conn = self.get_conn()
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        return count

    def count_subscribed(self) -> int:
        conn = self.get_conn()
        count = conn.execute("SELECT COUNT(*) FROM users WHERE subscribed = 1").fetchone()[0]
        conn.close()
        return count

    # ── JOBS ───────────────────────────────────────

    def save_job(self, job: Dict) -> bool:
        """Returns True if job is NEW (successfully inserted)"""
        conn = self.get_conn()
        try:
            conn.execute(
                """INSERT INTO jobs (title, company, link, category, location, source)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    job.get("title", ""),
                    job.get("company", ""),
                    job.get("link", ""),
                    job.get("category", "General"),
                    job.get("location", "Philippines"),
                    job.get("source", ""),
                ),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # duplicate
        finally:
            conn.close()

    def get_latest_jobs(self, limit: int = 10) -> List[Dict]:
        conn = self.get_conn()
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY date_found DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def count_jobs(self) -> int:
        conn = self.get_conn()
        count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        conn.close()
        return count

    def count_jobs_today(self) -> int:
        conn = self.get_conn()
        today = date.today().isoformat()
        count = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE date_found LIKE ?", (f"{today}%",)
        ).fetchone()[0]
        conn.close()
        return count
