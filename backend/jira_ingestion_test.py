from app.services.ingestors.jira_ingestor import JiraIngestor

source = {
    "source_url": "https://singhraghubir2311.atlassian.net",
    "username": "your_jira_email",
    "token": "your_jira_api_token",
    "project_key": "SCRUM",
    "jql": 'project = "SCRUM" ORDER BY created DESC',
    "maxresults": 5,
    "timeout": 60,
    "maxretries": 2,
    "source_name": "Jira",
    "source_type": "jira",
}

try:
    ingestor = JiraIngestor()
    docs = ingestor.extract(source)

    print(f"\nTotal docs fetched: {len(docs)}\n")

    for i, doc in enumerate(docs[:3], start=1):
        print("=" * 80)
        print(f"Document #{i}")
        print("ticketid:", doc.get("ticketid"))
        print("summary:", doc.get("summary"))
        print("status:", doc.get("status"))
        print("priority:", doc.get("priority"))
        print("source_url:", doc.get("source_url"))
        print("\nTEXT PREVIEW:")
        print(doc.get("text", "")[:1000])
        print("=" * 80)

except Exception as e:
    import traceback
    print("\nJira ingestion test failed:")
    print(str(e))
    traceback.print_exc()