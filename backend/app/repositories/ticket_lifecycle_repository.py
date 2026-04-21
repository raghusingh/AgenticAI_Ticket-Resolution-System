import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
import os

class TicketLifecycleRepository:
    """
    Persists and queries ticket closure / notification events
    in the local SQLite database.
    """

    def __init__(self):
        from app.core.db_path import get_db_path
        self.db_path = get_db_path()
        print(f"[TicketLifecycleRepository] DB path: {self.db_path}")
        print(f"[TicketLifecycleRepository] DB exists: {os.path.exists(self.db_path)}")

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        return conn

    # ------------------------------------------------------------------
    # ticket_events
    # ------------------------------------------------------------------

    def record_event(
        self,
        tenant_id: str,
        ticket_id: str,
        source_type: str,
        event_type: str,             # 'auto_closed' | 'notified' | 'skipped'
        confidence: float = 0.0,
        matched_ticket_id: Optional[str] = None,
        resolution: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> int:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ticket_events
                (tenant_id, ticket_id, source_type, event_type,
                 confidence, matched_ticket_id, resolution, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id, ticket_id, source_type, event_type,
                confidence, matched_ticket_id, resolution, reason,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        row_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return row_id

    def is_already_closed(self, tenant_id: str, ticket_id: str) -> bool:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM ticket_events
                WHERE tenant_id = ?
                AND ticket_id = ?
                AND event_type = 'auto_closed'
            """, (tenant_id, ticket_id))
            return cursor.fetchone()[0] > 0
        finally:
            conn.close()

    def get_closed_tickets(self, tenant_id: str) -> List[dict]:
        """
        Returns all closed tickets for a tenant with ticket_id,
        resolution and reason — used to populate the resolution dropdown.
        """
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ticket_id, resolution, reason, matched_ticket_id, created_at
                FROM ticket_events
                WHERE tenant_id = ?
                AND event_type = 'auto_closed'
                ORDER BY created_at DESC
            """, (tenant_id,))
            rows = cursor.fetchall()
            return [
                {
                    "ticket_id": r[0],
                    "resolution": r[1] or "",
                    "reason": r[2] or "",
                    "matched_ticket_id": r[3] or "",
                    "closed_at": r[4] or "",
                }
                for r in rows
            ]
        finally:
            conn.close()

    def list_events(self, tenant_id: str, limit: int = 50) -> List[dict]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM ticket_events
            WHERE tenant_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (tenant_id, limit),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    # ------------------------------------------------------------------
    # notification_log
    # ------------------------------------------------------------------

    def record_notification(
        self,
        tenant_id: str,
        ticket_id: str,
        assignee_email: Optional[str],
        channel: str,
        status: str,
        payload: Optional[dict] = None,
        error_message: Optional[str] = None,
    ) -> int:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO notification_log
                (tenant_id, ticket_id, assignee_email, channel,
                 status, payload, error_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id, ticket_id, assignee_email, channel,
                status,
                json.dumps(payload) if payload else None,
                error_message,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        row_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return row_id

    def list_notifications(self, tenant_id: str, limit: int = 50) -> List[dict]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM notification_log
            WHERE tenant_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (tenant_id, limit),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows