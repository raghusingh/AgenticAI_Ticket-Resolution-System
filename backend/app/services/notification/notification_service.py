"""
services/notification/notification_service.py

Flow:
  Scheduler RAG results (prefetched_tickets)
       │
       ▼
  Build HTML table
       │
       ▼
  Send email to assignee (or log if SMTP not configured)
       │
       ▼
  Save to notification_log
"""

import logging
from typing import List, Optional

from app.repositories.ticket_lifecycle_repository import TicketLifecycleRepository
from app.schemas.notification import NotifyRequest, NotifyResult, ResolutionRow
from app.services.notification.dispatcher import NotificationDispatcher

logger = logging.getLogger(__name__)


class NotificationService:

    def __init__(self):
        try:
            self.lifecycle_repo = TicketLifecycleRepository()
        except Exception as e:
            logger.warning(f"[NotificationService] DB init failed: {e} — DB logging disabled")
            self.lifecycle_repo = None

        self.dispatcher = NotificationDispatcher()

    def notify_on_ticket_created(self, request: NotifyRequest) -> NotifyResult:
        """
        1. Use pre-fetched RAG tickets from Scheduler (no second RAG call)
        2. Build resolution rows
        3. Send to assignee via email / mock
        4. Log to notification_log table
        """
        print(f"[NotificationService] Ticket={request.ticket_id} "
              f"Tenant={request.tenant_id} Assignee={request.assignee_email}")

        # ── 1. Use prefetched RAG tickets from Scheduler ──────────────────────
        tickets = request.prefetched_tickets or []
        print(f"[NotificationService] ✅ Using {len(tickets)} pre-fetched resolution(s) from Scheduler")

        if not tickets:
            print(f"[NotificationService] ⚠️  No resolutions to send for {request.ticket_id}")

        # ── 2. Build resolution rows ──────────────────────────────────────────
        resolutions: List[ResolutionRow] = []
        for t in tickets:
            try:
                row = ResolutionRow(
                    ticket_id=t.get("ticket_id", ""),
                    ticket_description=t.get("ticket_description") or t.get("description", ""),
                    resolution=t.get("resolution", ""),
                    root_cause=t.get("root_cause") or t.get("root cause", ""),
                    issue_type=t.get("issue_type") or t.get("type", ""),
                    status=t.get("status", ""),
                    priority=t.get("priority", ""),
                    confidence_score=float(t.get("confidence_score") or t.get("score") or 0.0),
                    source_url=t.get("source_url") or t.get("url") or None,
                    source_type=t.get("source_type") or t.get("source") or "",  # ✅ per-row source
                )
                resolutions.append(row)
            except Exception as e:
                print(f"[NotificationService] ⚠️  Row mapping failed: {e} | data: {t}")

        print(f"[NotificationService] Resolutions being sent: {len(resolutions)}")
        for r in resolutions:
            print(f"  → {r.ticket_id} | score={r.confidence_score:.4f} | "
                  f"{r.resolution[:60] if r.resolution else 'EMPTY'}")

        # ── 3. Send notification ──────────────────────────────────────────────
        dispatch = self.dispatcher.send(
            ticket_id=request.ticket_id,
            assignee_email=request.assignee_email,
            resolutions=resolutions,
            source_type=request.source_type or "",
            description=request.description or "",
        )
        print(f"[NotificationService] 📧 channel={dispatch['channel']} "
              f"status={dispatch['status']} message={dispatch['message']}")

        # ── 4. Log to DB ──────────────────────────────────────────────────────
        if self.lifecycle_repo:
            try:
                self.lifecycle_repo.record_notification(
                    tenant_id=request.tenant_id,
                    ticket_id=request.ticket_id,
                    assignee_email=request.assignee_email,
                    channel=dispatch["channel"],
                    status=dispatch["status"],
                    payload=dispatch.get("payload"),
                    error_message=None if dispatch["status"] != "failed"
                    else dispatch.get("message"),
                )
            except Exception as exc:
                print(f"[NotificationService] ⚠️  DB log failed: {exc}")
        else:
            print(f"[NotificationService] ⚠️  Skipping DB log — repository unavailable")

        return NotifyResult(
            ticket_id=request.ticket_id,
            assignee_email=request.assignee_email,
            channel=dispatch["channel"],
            status=dispatch["status"],
            resolutions=resolutions,
            message=dispatch["message"],
        )