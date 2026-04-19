from typing import Dict, List
import requests


class SharePointIngestor:
    def extract(self, source: Dict, secrets: Dict) -> List[str]:
        tenant_id = secrets.get("sharepoint_tenant_id") or source.get("tenant_id_secret")
        client_id = secrets.get("sharepoint_client_id") or source.get("client_id")
        client_secret = secrets.get("sharepoint_client_secret") or source.get("client_secret")

        if not tenant_id:
            raise ValueError("SharePoint tenant id missing")
        if not client_id:
            raise ValueError("SharePoint client id missing")
        if not client_secret:
            raise ValueError("SharePoint client secret missing")

        site_id = source.get("site_id")
        if not site_id:
            raise ValueError("SharePoint site_id missing")

        access_token = self._get_access_token(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )

        docs: List[str] = []

        list_id = source.get("list_id")
        drive_id = source.get("drive_id")

        if list_id:
            docs.extend(
                self._extract_list_items(
                    access_token=access_token,
                    site_id=site_id,
                    list_id=list_id,
                )
            )

        if drive_id:
            docs.extend(
                self._extract_drive_items(
                    access_token=access_token,
                    drive_id=drive_id,
                    source=source,
                )
            )

        return docs

    def _get_access_token(self, tenant_id: str, client_id: str, client_secret: str) -> str:
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

        response = requests.post(
            token_url,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
            timeout=60,
        )
        response.raise_for_status()

        token = response.json().get("access_token")
        if not token:
            raise ValueError("Failed to acquire SharePoint access token")

        return token

    def _extract_list_items(self, access_token: str, site_id: str, list_id: str) -> List[str]:
        url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_id}/items?expand=fields"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        docs: List[str] = []
        next_url = url

        while next_url:
            response = requests.get(next_url, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()

            for item in data.get("value", []):
                fields = item.get("fields", {}) or {}

                title = fields.get("Title", "")
                field_lines = [
                    f"{k}: {v}"
                    for k, v in fields.items()
                    if v is not None and str(v).strip()
                ]

                text = f"""
Source Type: SharePoint
Item Id: {item.get('id', '')}
Title: {title}

Fields:
{chr(10).join(field_lines)}
""".strip()

                docs.append(text)

            next_url = data.get("@odata.nextLink")

        return docs

    def _extract_drive_items(self, access_token: str, drive_id: str, source: Dict) -> List[str]:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        folder_id = source.get("folder_id")
        folder_path = source.get("folder_path")

        if folder_id:
            url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{folder_id}/children"
        elif folder_path:
            clean_path = folder_path.strip("/")
            url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{clean_path}:/children"
        else:
            url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/children"

        docs: List[str] = []
        next_url = url

        while next_url:
            response = requests.get(next_url, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()

            for item in data.get("value", []):
                if item.get("folder"):
                    continue

                file_name = item.get("name", "")
                web_url = item.get("webUrl", "")
                item_id = item.get("id", "")
                mime_type = ((item.get("file") or {}).get("mimeType", ""))

                text = f"""
Source Type: SharePoint
Drive Item Id: {item_id}
File Name: {file_name}
Mime Type: {mime_type}
Web Url: {web_url}
Last Modified: {item.get('lastModifiedDateTime', '')}
""".strip()

                docs.append(text)

            next_url = data.get("@odata.nextLink")

        return docs