"""
notification/dispatcher.py

Handles sending resolution tables to ticket assignees.
Supports:
  - SMTP e-mail (when SMTP_HOST is configured in .env)
  - Mock/log mode  (default when SMTP is not configured)

The HTML table format is always the same regardless of channel,
so the dispatcher is the single place where formatting lives.
"""

import json
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from app.schemas.notification import ResolutionRow

logger = logging.getLogger(__name__)


# ── HTML table builder ──────────────────────────────────────────────────────

def build_html_table(
    ticket_id: str,
    resolutions: List[ResolutionRow],
    source_type: str = "",
    description: str = "",
) -> str:
    """
    Returns a styled HTML e-mail body containing a resolution table.
    """
    rows_html = ""
    for i, r in enumerate(resolutions):
        bg = "#f9f9f9" if i % 2 == 0 else "#ffffff"
        score_pct = f"{r.confidence_score:.2f}"
        link = (
            f'<a href="{r.source_url}" target="_blank">{r.ticket_id}</a>'
            if r.source_url
            else r.ticket_id
        )
        rows_html += f"""
        <tr style="background:{bg}">
          <td style="{TD}">{_esc(r.source_type)}</td>
          <td style="{TD}">{link}</td>
          <td style="{TD}">{_esc(r.ticket_description)}</td>
          <td style="{TD}">{_esc(r.resolution)}</td>
          <td style="{TD}">{_esc(r.root_cause)}</td>
          <td style="{TD}">{_esc(r.issue_type)}</td>
          <td style="{TD}">{_esc(r.status)}</td>
          <td style="{TD}">{_esc(r.priority)}</td>
          <td style="{TD};text-align:center">{score_pct}</td>
        </tr>"""

    # New ticket summary box
    new_ticket_box = ""
    if description:
        new_ticket_box = f"""
  <table style="border-collapse:collapse;width:100%;font-size:13px;margin-bottom:20px;background:#f0f4ff;border:1px solid #c7d7f9;border-radius:6px">
    <tr>
      <td style="padding:10px 14px;font-weight:bold;color:#2563eb;white-space:nowrap;width:120px">Ticket ID</td>
      <td style="padding:10px 14px;color:#333">{_esc(ticket_id)}</td>
    </tr>
    <tr style="background:#e8eeff">
      <td style="padding:10px 14px;font-weight:bold;color:#2563eb;white-space:nowrap">Source</td>
      <td style="padding:10px 14px;color:#333">{_esc(source_type)}</td>
    </tr>
    <tr>
      <td style="padding:10px 14px;font-weight:bold;color:#2563eb;white-space:nowrap;vertical-align:top">Description</td>
      <td style="padding:10px 14px;color:#333">{_esc(description)}</td>
    </tr>
  </table>"""

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;color:#333;padding:24px">
  <h2 style="color:#2563eb">🎫 Ticket Resolution Suggestions</h2>
  <p>A new ticket has been raised. Below are the details and top matching resolutions from our knowledge base.</p>

  {new_ticket_box}

  <h3 style="color:#2563eb;margin-top:24px">Matching Resolutions</h3>
  <table style="border-collapse:collapse;width:100%;font-size:13px">
    <thead>
      <tr style="background:#2563eb;color:#fff">
        <th style="{TH}">Source</th>
        <th style="{TH}">Ticket ID</th>
        <th style="{TH}">Description</th>
        <th style="{TH}">Resolution</th>
        <th style="{TH}">Root Cause</th>
        <th style="{TH}">Type</th>
        <th style="{TH}">Status</th>
        <th style="{TH}">Priority</th>
        <th style="{TH}">Confidence</th>
      </tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>
  <p style="margin-top:16px;font-size:12px;color:#666">
    This is an automated message from the Ticket Resolution System.
    Please review and take appropriate action.
  </p>
</body>
</html>"""


TH = "padding:8px 12px;border:1px solid #ddd;text-align:left;white-space:nowrap"
TD = "padding:7px 10px;border:1px solid #ddd;vertical-align:top"


def _esc(text: Optional[str]) -> str:
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ── Dispatcher ──────────────────────────────────────────────────────────────

class NotificationDispatcher:
    """
    Send resolution notifications via SMTP or mock-log fallback.
    """

    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.sender_email = os.getenv("SMTP_FROM", self.smtp_user)

        # CC recipients — comma-separated in .env
        # SMTP_CC=manager@example.com,team@example.com
        cc_raw = os.getenv("SMTP_CC", "")
        self.cc_emails = [e.strip() for e in cc_raw.split(",") if e.strip()]

    @property
    def _smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    def send(
        self,
        ticket_id: str,
        assignee_email: Optional[str],
        resolutions: List[ResolutionRow],
        source_type: str = "",
        description: str = "",
    ) -> dict:
        """
        Dispatch a resolution table.

        Returns:
            {
                "channel":  "email" | "mock",
                "status":   "sent" | "mock_sent" | "failed",
                "message":  str,
                "payload":  dict   # what was attempted
            }
        """
        html_body = build_html_table(ticket_id, resolutions, source_type, description)
        subject = f"[Ticket Resolution] Suggestions for {ticket_id}"

        payload = {
            "ticket_id": ticket_id,
            "to": assignee_email,
            "subject": subject,
            "resolution_count": len(resolutions),
        }

        if not assignee_email:
            self.print_resolution_table(ticket_id, resolutions)
            return {
                "channel": "mock",
                "status": "mock_sent",
                "message": "No assignee email — resolution table printed to console.",
                "payload": payload,
            }

        if not self._smtp_configured:
            self.print_resolution_table(ticket_id, resolutions)
            return {
                "channel": "mock",
                "status": "mock_sent",
                "message": "SMTP not configured — resolution table printed to console.",
                "payload": payload,
            }

        # ── Real SMTP send ────────────────────────────────────────────
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.sender_email
            msg["To"] = assignee_email
            if self.cc_emails:
                msg["Cc"] = ", ".join(self.cc_emails)
            msg.attach(MIMEText(html_body, "html"))

            # Send to assignee + all CC recipients
            all_recipients = [assignee_email] + self.cc_emails
            logger.info("Sending to: %s | CC: %s", assignee_email, self.cc_emails)

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.sender_email, all_recipients, msg.as_string())

            logger.info("Resolution e-mail sent for %s → %s", ticket_id, assignee_email)
            return {
                "channel": "email",
                "status": "sent",
                "message": f"Resolution sent to {assignee_email} (CC: {', '.join(self.cc_emails) or 'none'}).",
                "payload": payload,
            }

        except Exception as exc:
            logger.error("SMTP send failed for %s: %s", ticket_id, exc)
            return {
                "channel": "email",
                "status": "failed",
                "message": str(exc),
                "payload": payload,
            }

    def _log_mock(self, ticket_id: str, html_body: str) -> None:
        logger.info("SMTP not configured — printing resolution table to console.")

    def print_resolution_table(self, ticket_id: str, resolutions) -> None:
        """
        Print resolution table to console with exactly the same 9 columns as the UI:
        Source | Ticket ID | Description | Resolution | Root Cause |
        Type | Status | Priority | Confidence
        """
        W = 120  # total width

        print("\n" + "=" * W)
        print(f"  RESOLUTION SUGGESTIONS FOR NEW TICKET: {ticket_id}")
        print("=" * W)

        if not resolutions:
            print("  ⚠️  No matching resolutions found in knowledge base.")
            print("=" * W + "\n")
            return

        # Column definitions: (header, field, width)
        cols = [
            ("Source",      "source",             12),
            ("Ticket ID",   "ticket_id",          12),
            ("Description", "ticket_description", 28),
            ("Resolution",  "resolution",         30),
            ("Root Cause",  "root_cause",         22),
            ("Type",        "issue_type",         12),
            ("Status",      "status",             10),
            ("Priority",    "priority",            9),
            ("Confidence",  "confidence_score",    10),
        ]

        def trunc(val, w):
            s = str(val or "").strip().replace("\n", " ")
            return (s[:w-2] + "..") if len(s) > w else s

        # Header row
        header = " | ".join(f"{h:<{w}}" for h, _, w in cols)
        divider = "-+-".join("-" * w for _, _, w in cols)
        print(f"  {header}")
        print(f"  {divider}")

        for i, r in enumerate(resolutions, 1):
            vals = []
            for header_name, field, w in cols:
                if field == "confidence_score":
                    v = f"{getattr(r, field, 0):.2f}"
                else:
                    v = trunc(getattr(r, field, ""), w)
                vals.append(f"{v:<{w}}")
            print(f"  {' | '.join(vals)}")
            if i < len(resolutions):
                print(f"  {divider}")

        print(f"\n  Total: {len(resolutions)} matching resolution(s) found")
        print("=" * W + "\n")