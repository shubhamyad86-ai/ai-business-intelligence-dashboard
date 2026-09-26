"""SQLite persistence for users and chat audit history."""
from __future__ import annotations
import os, sqlite3
from dotenv import load_dotenv
load_dotenv()
from pathlib import Path

DB_PATH = Path(os.getenv("DATABASE_PATH", Path(__file__).resolve().parent.parent / "data" / "app.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def connect():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with connect() as con:
        con.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        con.execute("CREATE TABLE IF NOT EXISTS chat_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, question TEXT NOT NULL, answer TEXT NOT NULL, latency_ms REAL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        con.commit()

def get_user(username: str):
    with connect() as con:
        row = con.execute("SELECT username, password_hash, role, created_at FROM users WHERE username=?", (username,)).fetchone()
        return dict(row) if row else None

def create_user(username: str, password_hash: str, role: str = "user") -> bool:
    try:
        with connect() as con:
            con.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)", (username,password_hash,role))
            con.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def log_chat(username, question, answer, latency_ms):
    with connect() as con:
        con.execute("INSERT INTO chat_logs(username,question,answer,latency_ms) VALUES(?,?,?,?)", (username,question,answer,latency_ms))
        con.commit()

def recent_logs(limit=50):
    with connect() as con:
        return [dict(r) for r in con.execute("SELECT id,username,question,answer,latency_ms,created_at FROM chat_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]

init_db()
