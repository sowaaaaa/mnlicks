import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = str(Path(__file__).parent / 'subscriptions.db')


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            plan_key TEXT,
            expires_at TEXT,
            invite_link TEXT,
            status TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    return conn


def upsert_subscription(user_id: int, username: str, plan_key: str, expires_at: datetime, invite_link: str):
    conn = _connect()
    with conn:
        conn.execute('''
            INSERT INTO subscriptions (user_id, username, plan_key, expires_at, invite_link, status)
            VALUES (?, ?, ?, ?, ?, 'active')
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                plan_key=excluded.plan_key,
                expires_at=excluded.expires_at,
                invite_link=excluded.invite_link,
                status='active'
        ''', (user_id, username, plan_key, expires_at.isoformat(), invite_link))
    conn.close()


def get_expired(now: datetime) -> list[tuple[int, str]]:
    conn = _connect()
    rows = conn.execute(
        "SELECT user_id, plan_key FROM subscriptions WHERE status = 'active' AND expires_at <= ?",
        (now.isoformat(),),
    ).fetchall()
    conn.close()
    return rows


def mark_status(user_id: int, status: str):
    conn = _connect()
    with conn:
        conn.execute('UPDATE subscriptions SET status = ? WHERE user_id = ?', (status, user_id))
    conn.close()


def get_setting(key: str, default: str | None = None) -> str | None:
    conn = _connect()
    row = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key: str, value: str):
    conn = _connect()
    with conn:
        conn.execute('''
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        ''', (key, value))
    conn.close()
