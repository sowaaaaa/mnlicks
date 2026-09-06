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
    conn.execute('''
        CREATE TABLE IF NOT EXISTS grandfather_members (
            user_id INTEGER PRIMARY KEY,
            username TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS platega_payments (
            transaction_id TEXT PRIMARY KEY,
            user_id INTEGER,
            username TEXT,
            plan_key TEXT,
            amount INTEGER,
            status TEXT,
            created_at TEXT,
            updated_at TEXT
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


def has_active_subscription(user_id: int) -> bool:
    conn = _connect()
    row = conn.execute(
        "SELECT 1 FROM subscriptions WHERE user_id = ? AND status = 'active'",
        (user_id,),
    ).fetchone()
    conn.close()
    return row is not None


def add_grandfather_members(entries: list[tuple[int, str | None]]):
    conn = _connect()
    with conn:
        conn.executemany(
            'INSERT OR IGNORE INTO grandfather_members (user_id, username) VALUES (?, ?)',
            entries,
        )
    conn.close()


def get_grandfather_members() -> list[tuple[int, str | None]]:
    conn = _connect()
    rows = conn.execute('SELECT user_id, username FROM grandfather_members').fetchall()
    conn.close()
    return rows


def remove_grandfather_member(user_id: int):
    conn = _connect()
    with conn:
        conn.execute('DELETE FROM grandfather_members WHERE user_id = ?', (user_id,))
    conn.close()


def save_platega_payment(
    transaction_id: str,
    user_id: int,
    username: str | None,
    plan_key: str,
    amount: int,
    status: str = 'PENDING',
):
    now = datetime.now().isoformat()
    conn = _connect()
    with conn:
        conn.execute('''
            INSERT INTO platega_payments (
                transaction_id, user_id, username, plan_key, amount, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(transaction_id) DO UPDATE SET
                user_id=excluded.user_id,
                username=excluded.username,
                plan_key=excluded.plan_key,
                amount=excluded.amount,
                status=excluded.status,
                updated_at=excluded.updated_at
        ''', (transaction_id, user_id, username, plan_key, amount, status, now, now))
    conn.close()


def get_pending_platega_payments() -> list[tuple[str, int, str | None, str, int]]:
    conn = _connect()
    rows = conn.execute('''
        SELECT transaction_id, user_id, username, plan_key, amount
        FROM platega_payments
        WHERE status = 'PENDING'
    ''').fetchall()
    conn.close()
    return rows


def get_platega_payment(transaction_id: str) -> tuple[str, int, str | None, str, int, str] | None:
    conn = _connect()
    row = conn.execute('''
        SELECT transaction_id, user_id, username, plan_key, amount, status
        FROM platega_payments
        WHERE transaction_id = ?
    ''', (transaction_id,)).fetchone()
    conn.close()
    return row


def mark_platega_payment_status(transaction_id: str, status: str):
    conn = _connect()
    with conn:
        conn.execute(
            'UPDATE platega_payments SET status = ?, updated_at = ? WHERE transaction_id = ?',
            (status, datetime.now().isoformat(), transaction_id),
        )
    conn.close()
