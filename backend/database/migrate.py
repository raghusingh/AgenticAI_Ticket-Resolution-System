"""
Database migration: adds ticket_events and notification_log tables
for auto-closure and notification features.
Run once: python database/migrate.py
"""

import sqlite3
import os

# Always resolve to backend/database/ticket.db regardless of where script is called from
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ticket.db")


def migrate():
    print("🔄 Running database migrations...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # -------------------------------------------------------
    # TICKET EVENTS TABLE
    # Tracks auto-closure decisions per ticket per tenant
    # -------------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ticket_events (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id     TEXT    NOT NULL,
        ticket_id     TEXT    NOT NULL,
        source_type   TEXT    NOT NULL,          -- 'jira' | 'sharepoint_local'
        event_type    TEXT    NOT NULL,          -- 'auto_closed' | 'notified' | 'skipped'
        confidence    REAL    DEFAULT 0.0,
        matched_ticket_id TEXT,                 -- best-match ticket from RAG
        resolution    TEXT,
        reason        TEXT,
        created_at    TEXT    NOT NULL
    )
    """)

    # -------------------------------------------------------
    # NOTIFICATION LOG TABLE
    # Records every outgoing resolution e-mail / webhook
    # -------------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notification_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id       TEXT NOT NULL,
        ticket_id       TEXT NOT NULL,
        assignee_email  TEXT,
        channel         TEXT NOT NULL,          -- 'email' | 'webhook' | 'mock'
        status          TEXT NOT NULL,          -- 'sent' | 'failed' | 'mock_sent'
        payload         TEXT,                   -- JSON string of what was sent
        error_message   TEXT,
        created_at      TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()
    print("✅ Migrations applied successfully.")


if __name__ == "__main__":
    migrate()