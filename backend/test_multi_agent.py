# test_multi_agent.py
import sys, os
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()

from app.services.agent.agents.coordinator_agent import run_multi_agent_system

result = run_multi_agent_system(
    tenant_id      = "client-a",
    ticket_id      = "SCRUM-TEST-1",
    source_type    = "jira",
    description    = "500 Internal Error on WebSite after deployment",
    assignee_email = "singh.raghubir2311@gmail.com",
)

print("\n" + "="*50)
print("MULTI-AGENT RESULT")
print("="*50)
print(f"Ingestion   : {result['ingestion_status']}")
print(f"Resolution  : {result['resolution_status']} (conf={result['best_confidence']:.4f})")
print(f"Notification: {result['notification_status']}")
print(f"Closure     : {result['closure_decision']}")
print(f"Steps done  : {result['steps_completed']}")
print(f"Errors      : {result['errors']}")
print(f"Summary     : {result['final_summary']}")