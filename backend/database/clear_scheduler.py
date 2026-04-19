"""
Utility script to clear scheduler_processed table.
Run from anywhere inside the project:

    python database/clear_scheduler.py              # list all
    python database/clear_scheduler.py --all        # clear everything
    python database/clear_scheduler.py --ticket SCRUM-9
    python database/clear_scheduler.py --source jira
"""

import sqlite3
import sys
from pathlib import Path

# Always resolve DB path relative to THIS file — works regardless of where you run from
DB_FILE = Path(__file__).resolve().parent / "ticket.db"


def get_conn():
    conn = sqlite3.connect(str(DB_FILE))
    # Create table if it doesn't exist yet
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduler_processed (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id    TEXT NOT NULL,
            source_type  TEXT NOT NULL,
            ticket_id    TEXT NOT NULL,
            content_hash TEXT,
            processed_at TEXT NOT NULL,
            UNIQUE(tenant_id, source_type, ticket_id)
        )
    """)
    conn.commit()
    return conn


def list_all():
    conn = get_conn()
    rows = conn.execute(
        "SELECT ticket_id, source_type, tenant_id, processed_at FROM scheduler_processed ORDER BY processed_at DESC"
    ).fetchall()
    conn.close()
    print(f"\nDB path: {DB_FILE}")
    print(f"\n{'Ticket ID':<15} {'Source':<20} {'Tenant':<15} {'Processed At'}")
    print("-" * 75)
    for row in rows:
        print(f"{row[0]:<15} {row[1]:<20} {row[2]:<15} {row[3]}")
    print(f"\nTotal: {len(rows)} record(s)")


def clear_all():
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM scheduler_processed").fetchone()[0]
    conn.execute("DELETE FROM scheduler_processed")
    conn.commit()
    conn.close()
    print(f"✅ Cleared {count} record(s) from scheduler_processed.")
    print(f"   DB: {DB_FILE}")


def clear_ticket(ticket_id: str):
    conn = get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM scheduler_processed WHERE ticket_id = ?", (ticket_id,)
    ).fetchone()[0]
    conn.execute("DELETE FROM scheduler_processed WHERE ticket_id = ?", (ticket_id,))
    conn.commit()
    conn.close()
    print(f"✅ Cleared {count} record(s) for ticket: {ticket_id}")


def clear_source(source_type: str):
    conn = get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM scheduler_processed WHERE source_type = ?", (source_type,)
    ).fetchone()[0]
    conn.execute("DELETE FROM scheduler_processed WHERE source_type = ?", (source_type,))
    conn.commit()
    conn.close()
    print(f"✅ Cleared {count} record(s) for source: {source_type}")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        list_all()
        print("\nOptions:")
        print("  python database/clear_scheduler.py --all")
        print("  python database/clear_scheduler.py --ticket SCRUM-9")
        print("  python database/clear_scheduler.py --source jira")

    elif "--all" in args:
        clear_all()

    elif "--ticket" in args:
        idx = args.index("--ticket")
        clear_ticket(args[idx + 1])

    elif "--source" in args:
        idx = args.index("--source")
        clear_source(args[idx + 1])