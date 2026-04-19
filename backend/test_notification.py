"""
Test script — directly tests the full flow:
  description → RAG search → resolution table → console output

Run from backend/ folder:
    python test_notification.py
"""
import os, sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

TENANT_ID   = "client-a"
TICKET_ID   = "TEST-001"
SOURCE_TYPE = "jira"
DESCRIPTION = "Login fails after password reset. User cannot authenticate."

print(f"\n{'='*60}")
print(f"Testing full notification flow")
print(f"Ticket     : {TICKET_ID}")
print(f"Description: {DESCRIPTION}")
print(f"{'='*60}\n")

from app.schemas.notification import NotifyRequest
from app.services.notification.notification_service import NotificationService

result = NotificationService().notify_on_ticket_created(
    NotifyRequest(
        tenant_id=TENANT_ID,
        ticket_id=TICKET_ID,
        source_type=SOURCE_TYPE,
        description=DESCRIPTION,
        assignee_email=None,
        top_k=5,
    )
)

print(f"\nResult: channel={result.channel} status={result.status}")
print(f"Resolutions in table: {len(result.resolutions)}")
