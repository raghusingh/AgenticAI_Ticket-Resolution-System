import sqlite3
import os
import hashlib
from datetime import datetime

DB_FILE = "database/ticket.db"


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def seed_db():
    print("🚀 Seeding database...")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # -----------------------------
    # USERS TABLE
    # -----------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        created_at TEXT
    )
    """)

    # -----------------------------
    # SESSIONS TABLE
    # -----------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        session_id TEXT,
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    # -----------------------------
    # CHAT HISTORY (Optional but useful)
    # -----------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        session_id TEXT,
        question TEXT,
        response TEXT,
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    # -----------------------------
    # INSERT DEFAULT USERS
    # -----------------------------
    users = [
        ("admin", hash_password("admin123")),
        ("raghubir", hash_password("raghu123")),
        ("testuser", hash_password("test123")),
    ]

    for username, password in users:
        cursor.execute("""
        INSERT OR IGNORE INTO users (username, password, created_at)
        VALUES (?, ?, ?)
        """, (username, password, datetime.utcnow().isoformat()))

    conn.commit()
    conn.close()

    print("✅ Database seeded successfully!")


if __name__ == "__main__":
    seed_db()