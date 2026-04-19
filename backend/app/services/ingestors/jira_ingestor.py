from typing import Dict, List, Any, Optional
import time
import requests
from requests.auth import HTTPBasicAuth
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class JiraIngestor:
    def extract(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        print("Ingestion of Jira has started")

        base_url = (source.get("source_url") or "").strip()
        username = (source.get("username") or "").strip()
        token = (source.get("token") or "").strip()
        project_key = (source.get("project_key") or "").strip()

        if not base_url:
            raise ValueError("Jira source_url missing")
        if not username:
            raise ValueError("Jira username missing")
        if not token:
            raise ValueError("Jira token missing")
        if not project_key and not (source.get("jql") or "").strip():
            raise ValueError("Jira project_key missing")

        jql = (source.get("jql") or "").strip()
        if not jql and project_key:
            jql = f'project = "{project_key}" ORDER BY created DESC'

        if jql.endswith('"') and jql.count('"') % 2 == 1:
            jql = jql[:-1].strip()

        max_results = int(source.get("maxresults", 50) or 50)
        if max_results <= 0:
            max_results = 50
        max_results = min(max_results, 100)

        timeout = int(source.get("timeout", 60) or 60)
        max_retries = int(source.get("maxretries", 3) or 3)

        search_url = f"{base_url.rstrip('/')}/rest/api/3/search/jql"
        auth = HTTPBasicAuth(username, token)

        print("DEBUG base_url:", base_url)
        print("DEBUG project_key:", project_key)
        print("DEBUG jql:", jql)
        print("DEBUG search_url:", search_url)

        docs: List[Dict[str, Any]] = []
        next_page_token: Optional[str] = None

        while True:
            body = {
                "jql": jql,
                "maxResults": max_results,
                "fields": [
                    "summary",
                    "description",
                    "status",
                    "priority",
                    "issuetype",
                    "created",
                    "updated",
                    "resolution",
                    "resolutiondate",
                ],
            }

            if next_page_token:
                body["nextPageToken"] = next_page_token

            response = self.request_with_retry(
                method="POST",
                url=search_url,
                auth=auth,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json_body=body,
                timeout=timeout,
                verify=False,
                max_retries=max_retries,
            )

            print("DEBUG Jira response status:", response.status_code)

            if response.status_code == 401:
                raise ValueError("Jira authentication failed while fetching issues")

            if response.status_code == 400:
                raise ValueError(
                    f"Jira returned 400 Bad Request. Please verify project_key/jql. Response: {response.text}"
                )

            if response.status_code == 404:
                raise ValueError(
                    f"Jira returned 404 Not Found. Please verify base URL or endpoint: {search_url}"
                )

            if response.status_code == 410:
                raise ValueError(
                    "Jira returned 410 Gone. This tenant no longer supports the old search endpoint."
                )

            response.raise_for_status()
            data = response.json() or {}

            issues = data.get("issues") or []
            print("DEBUG Jira issues fetched in page:", len(issues))

            if not issues:
                break

            for issue in issues:
                key = issue.get("key", "")
                fields = issue.get("fields") or {}

                summary = (fields.get("summary") or "").strip()
                status = ((fields.get("status") or {}).get("name") or "").strip()
                priority = ((fields.get("priority") or {}).get("name") or "").strip()
                issuetype = ((fields.get("issuetype") or {}).get("name") or "").strip()
                created = (fields.get("created") or "").strip()
                updated = (fields.get("updated") or "").strip()

                raw_description = fields.get("description")
                description = self.jira_description_to_text(raw_description)
                if not description:
                    description = str(raw_description or "").strip()

                resolution_obj = fields.get("resolution") or {}
                resolution_name = (resolution_obj.get("name") or "").strip()
                resolution_date = (fields.get("resolutiondate") or "").strip()

                # ── Fetch comments for this issue ─────────────────────────
                comments_text = self._fetch_comments(
                    base_url=base_url,
                    issue_key=key,
                    auth=auth,
                    timeout=timeout,
                )

                # IMPORTANT:
                # Summary = short problem statement
                # Detailed Description = long explanation / work details
                # Resolution = keep Jira's raw resolution value only for reference
                # Comments = capture resolution added via API or manually
                text = (
                    f"Issue Key: {key}\n"
                    f"Type: {issuetype}\n"
                    f"Summary: {summary}\n"
                    f"Status: {status}\n"
                    f"Priority: {priority}\n"
                    f"Created: {created}\n"
                    f"Updated: {updated}\n"
                    f"Resolution: {resolution_name}\n"
                    f"Resolution Date: {resolution_date}\n"
                    f"Detailed Description: {description}\n"
                    f"Comments: {comments_text}\n"
                ).strip()

                docs.append(
                    {
                        "text": text,
                        "ticketid": key,
                        "issuetype": issuetype,
                        "summary": summary,
                        "status": status,
                        "priority": priority,
                        "resolution": resolution_name,
                        "created": created,
                        "updated": updated,
                        "source_name": source.get("source_name", "Jira"),
                        "source_type": source.get("source_type", "jira"),
                        "source_url": base_url,
                    }
                )

            next_page_token = data.get("nextPageToken")
            is_last = data.get("isLast")  # None if field missing

            # If isLast is not in response, determine by checking if
            # we got fewer issues than requested (means we're on last page)
            if is_last is None:
                is_last = len(issues) < max_results

            if is_last or not next_page_token:
                break

        print(f"Total Jira docs fetched: {len(docs)}")
        return docs

    def _fetch_comments(
        self,
        base_url: str,
        issue_key: str,
        auth: HTTPBasicAuth,
        timeout: int = 30,
    ) -> str:
        """
        Fetch all comments for a Jira issue and return them as a
        single concatenated string. Captures resolutions added via API.
        """
        url = f"{base_url.rstrip('/')}/rest/api/3/issue/{issue_key}/comment"
        try:
            resp = requests.get(
                url,
                auth=auth,
                headers={"Accept": "application/json"},
                timeout=timeout,
                verify=False,
            )
            if resp.status_code != 200:
                return ""

            data = resp.json()
            comments = data.get("comments") or []
            parts = []
            for c in comments:
                body = c.get("body")
                # body can be Atlassian Document Format (dict) or plain string
                if isinstance(body, dict):
                    text = self.jira_description_to_text(body)
                else:
                    text = str(body or "").strip()
                if text:
                    author = (c.get("author") or {}).get("displayName", "")
                    parts.append(f"[{author}]: {text}")

            return " | ".join(parts)

        except Exception as exc:
            print(f"[JiraIngestor] ⚠️  Failed to fetch comments for {issue_key}: {exc}")
            return ""

    def request_with_retry(
        self,
        method: str,
        url: str,
        auth,
        headers: Dict[str, str],
        timeout: int,
        verify: bool,
        max_retries: int,
        params: Dict[str, Any] = None,
        json_body: Dict[str, Any] = None,
    ) -> requests.Response:
        last_exception = None

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    auth=auth,
                    headers=headers,
                    params=params,
                    json=json_body,
                    timeout=timeout,
                    verify=verify,
                )

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_seconds = (
                        int(retry_after)
                        if retry_after and retry_after.isdigit()
                        else min(2 ** attempt, 30)
                    )
                    time.sleep(wait_seconds)
                    continue

                if response.status_code in (500, 502, 503, 504):
                    if attempt < max_retries:
                        time.sleep(min(2 ** attempt, 10))
                        continue

                return response

            except requests.exceptions.ReadTimeout as exc:
                last_exception = exc
                if attempt < max_retries:
                    time.sleep(min(2 ** attempt, 10))
                    continue
                raise
            except requests.exceptions.ConnectionError as exc:
                last_exception = exc
                if attempt < max_retries:
                    time.sleep(min(2 ** attempt, 10))
                    continue
                raise

        if last_exception:
            raise last_exception

        raise RuntimeError("Jira request failed unexpectedly")

    def jira_description_to_text(self, description: Any) -> str:
        if not description:
            return ""

        parts: List[str] = []

        def walk(node: Any):
            if isinstance(node, dict):
                node_type = node.get("type")

                if node_type == "text":
                    text = node.get("text", "")
                    if text:
                        parts.append(text)

                elif node_type == "hardBreak":
                    parts.append("\n")

                elif node_type in ("paragraph", "heading", "blockquote", "panel", "listItem"):
                    for item in node.get("content") or []:
                        walk(item)
                    parts.append("\n")

                elif node_type in ("bulletList", "orderedList", "doc"):
                    for item in node.get("content") or []:
                        walk(item)

                else:
                    for item in node.get("content") or []:
                        walk(item)

            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(description)

        lines = []
        for line in "".join(parts).splitlines():
            cleaned = " ".join(line.split()).strip()
            if cleaned:
                lines.append(cleaned)

        return "\n".join(lines)