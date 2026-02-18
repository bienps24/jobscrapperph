import sqlite3
import os
from datetime import date
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
        conn.executescript("""
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
                category    TEXT DEFAULT 'General',
                location    TEXT DEFAULT 'Philippines',
                salary      TEXT,
                source      TEXT,
                date_found  TEXT DEFAULT (datetime('now', '+8 hours'))
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_date     ON jobs(date_found DESC);
            CREATE INDEX IF NOT EXISTS idx_jobs_category ON jobs(category);
            CREATE INDEX IF NOT EXISTS idx_jobs_source   ON jobs(source);
            CREATE INDEX IF NOT EXISTS idx_users_sub     ON users(subscribed);
        """)
        conn.commit()
        conn.close()

    def add_user(self, user_id: int, name: str) -> bool:
        conn = self.get_conn()
        cursor = conn.execute(
            "INSERT OR IGNORE INTO users (user_id, name) VALUES (?, ?)",
            (user_id, name),
        )
        conn.commit()
        is_new = cursor.rowcount > 0
        conn.close()
        return is_new

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
        n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        return n

    def count_subscribed(self) -> int:
        conn = self.get_conn()
        n = conn.execute("SELECT COUNT(*) FROM users WHERE subscribed = 1").fetchone()[0]
        conn.close()
        return n

    def save_job(self, job: Dict) -> bool:
        conn = self.get_conn()
        try:
            conn.execute(
                "INSERT INTO jobs (title, company, link, category, location, salary, source) VALUES (?,?,?,?,?,?,?)",
                (
                    job.get("title", ""),
                    job.get("company", ""),
                    job.get("link", ""),
                    job.get("category", "General"),
                    job.get("location", "Philippines"),
                    job.get("salary"),
                    job.get("source", ""),
                ),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def get_latest_jobs(self, limit: int = 15) -> List[Dict]:
        conn = self.get_conn()
        rows = conn.execute("SELECT * FROM jobs ORDER BY date_found DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_latest_jobs_by_category(self, category: str, limit: int = 15) -> List[Dict]:
        conn = self.get_conn()
        rows = conn.execute(
            "SELECT * FROM jobs WHERE category = ? ORDER BY date_found DESC LIMIT ?",
            (category, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def count_jobs(self) -> int:
        conn = self.get_conn()
        n = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        conn.close()
        return n

    def count_jobs_today(self) -> int:
        conn = self.get_conn()
        today = date.today().isoformat()
        n = conn.execute("SELECT COUNT(*) FROM jobs WHERE date_found LIKE ?", (f"{today}%",)).fetchone()[0]
        conn.close()
        return n

    def count_by_source(self) -> List[Dict]:
        conn = self.get_conn()
        rows = conn.execute(
            "SELECT source, COUNT(*) as count FROM jobs GROUP BY source ORDER BY count DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def delete_user(self, user_id: int):
        """Para sa /deletedata command — GDPR compliance."""
        conn = self.get_conn()
        conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
