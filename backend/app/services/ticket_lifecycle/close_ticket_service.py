"""
services/ticket_lifecycle/close_ticket_service.py

Manually closes a ticket by:
  1. Looking up the Jira config for the tenant
  2. Calling the Jira REST API to transition ticket to Done
  3. Adding a comment to the Jira ticket
  4. Recording the closure event in ticket_events (DB)
"""

import logging
from pathlib import Path
from typing import Optional
import json

import requests
from requests.auth import HTTPBasicAuth

from app.repositories.ticket_lifecycle_repository import TicketLifecycleRepository

logger = logging.getLogger(__name__)


def _load_raw_config(tenant_id: str) -> Optional[dict]:
    """Load raw tenant config JSON (same pattern as notification_service)."""
    config_path = (
        Path(__file__).resolve().parents[3]
        / "config_store"
        / f"{tenant_id}_rag_config.json"
    )
    if not config_path.exists():
        return None
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_jira_transition_id(
    jira_url: str,
    ticket_id: str,
    auth: HTTPBasicAuth,
    target_name: str = "Done",
) -> Optional[str]:
    """
    Fetch available transitions for the ticket and return the ID
    for the transition named 'Done' (or closest match).
    """
    url = f"{jira_url.rstrip('/')}/rest/api/2/issue/{ticket_id}/transitions"
    try:
        resp = requests.get(url, auth=auth, timeout=10, verify=False)
        resp.raise_for_status()
        transitions = resp.json().get("transitions", [])
        for t in transitions:
            if t.get("name", "").lower() == target_name.lower():
                return t["id"]
        # Fallback: return first transition that contains 'done' or 'close'
        for t in transitions:
            name = t.get("name", "").lower()
            if "done" in name or "close" in name or "resolved" in name:
                return t["id"]
        logger.warning("No 'Done' transition found. Available: %s",
                       [t.get("name") for t in transitions])
        return None
    except Exception as exc:
        logger.error("Failed to fetch Jira transitions for %s: %s", ticket_id, exc)
        return None


class CloseTicketService:

    def __init__(self):
        self.lifecycle_repo = TicketLifecycleRepository()

    def close(
        self,
        tenant_id: str,
        ticket_id: str,
        reason: str = "Manually closed via API.",
    ) -> dict:
        """
        Close a Jira ticket and record the event in DB.

        Returns a result dict with status and details.
        """
        print(f"[CloseTicketService] Closing ticket={ticket_id} tenant={tenant_id}")

        # ── 1. Guard: already closed? ─────────────────────────────────────────
        if self.lifecycle_repo.is_already_closed(tenant_id, ticket_id):
            return {
                "ticket_id": ticket_id,
                "status": "skipped",
                "message": f"Ticket {ticket_id} is already closed.",
                "jira_updated": False,
            }

        # ── 2. Load tenant config for Jira credentials ────────────────────────
        raw = _load_raw_config(tenant_id)
        if not raw:
            return {
                "ticket_id": ticket_id,
                "status": "failed",
                "message": f"Tenant config not found for {tenant_id}.",
                "jira_updated": False,
            }

        # Extract Jira source config
        jira_source = None
        for source in raw.get("data_sources", []):
            if (source.get("source_type") or "").lower() == "jira" and source.get("is_enabled", True):
                jira_source = source
                break

        if not jira_source:
            return {
                "ticket_id": ticket_id,
                "status": "failed",
                "message": "No enabled Jira source found in tenant config.",
                "jira_updated": False,
            }

        jira_url   = jira_source.get("source_url", "").rstrip("/")
        jira_user  = jira_source.get("username", "")
        jira_token = jira_source.get("token", "")

        print(f"[CloseTicketService] Jira URL  : {jira_url}")
        print(f"[CloseTicketService] Jira User : {jira_user}")
        print(f"[CloseTicketService] Jira Token: {'set' if jira_token else 'MISSING'}")

        if not all([jira_url, jira_user, jira_token]):
            return {
                "ticket_id": ticket_id,
                "status": "failed",
                "message": "Jira credentials incomplete (url/user/token).",
                "jira_updated": False,
            }

        auth = HTTPBasicAuth(jira_user, jira_token)
        jira_updated = False

        # ── 3. Get the 'Done' transition ID ───────────────────────────────────
        transition_id = _get_jira_transition_id(jira_url, ticket_id, auth, "Done")

        if transition_id:
            # ── 4. Transition ticket to Done ──────────────────────────────────
            trans_url = f"{jira_url}/rest/api/2/issue/{ticket_id}/transitions"
            try:
                resp = requests.post(
                    trans_url,
                    auth=auth,
                    json={"transition": {"id": transition_id}},
                    timeout=10,
                    verify=False,
                )
                if resp.status_code in (200, 204):
                    print(f"[CloseTicketService] ✅ Jira ticket {ticket_id} transitioned to Done")
                    jira_updated = True
                else:
                    print(f"[CloseTicketService] ⚠️  Jira transition failed: {resp.status_code} {resp.text}")
            except Exception as exc:
                print(f"[CloseTicketService] ❌ Jira transition error: {exc}")
        else:
            print(f"[CloseTicketService] ⚠️  Could not find Done transition — skipping Jira update")

        # ── 5. Add comment to Jira ticket ─────────────────────────────────────
        comment_url = f"{jira_url}/rest/api/2/issue/{ticket_id}/comment"
        try:
            requests.post(
                comment_url,
                auth=auth,
                json={"body": f"Reason: {reason}"},
                timeout=10,
                verify=False,
            )
            print(f"[CloseTicketService] ✅ Comment added to {ticket_id}")
        except Exception as exc:
            print(f"[CloseTicketService] ⚠️  Failed to add comment: {exc}")

        # ── 6. Record closure in DB ───────────────────────────────────────────
        try:
            self.lifecycle_repo.record_event(
                tenant_id=tenant_id,
                ticket_id=ticket_id,
                source_type="jira",
                event_type="auto_closed",
                confidence=1.0,       # manual close = full confidence
                reason=reason,
            )
            print(f"[CloseTicketService] ✅ DB event recorded for {ticket_id}")
        except Exception as exc:
            print(f"[CloseTicketService] ⚠️  DB record failed: {exc}")

        return {
            "ticket_id": ticket_id,
            "status": "closed",
            "message": f"Ticket {ticket_id} successfully closed.",
            "jira_updated": jira_updated,
            "reason": reason,
        }
