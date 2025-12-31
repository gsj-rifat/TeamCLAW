import base64
import httpx
from typing import List, Optional
from src.core.interfaces.tickets import TicketProvider
from src.infrastructure.config import settings

class JiraAdapter(TicketProvider):
    def __init__(self, 
                 base_url: str = settings.jira_base_url,
                 email: str = settings.jira_email,
                 api_token: str = settings.jira_api_token):
        self.base_url = (base_url or "").rstrip("/")
        self.email = email
        self.api_token = api_token

    def _get_auth_header(self) -> dict:
        if not self.email or not self.api_token:
            return {}
        auth_str = f"{self.email}:{self.api_token}"
        b64_auth = base64.b64encode(auth_str.encode()).decode()
        return {
            "Authorization": f"Basic {b64_auth}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    async def create_ticket(self, project_key: str, summary: str, description: str, labels: List[str]) -> str:
        if not self.base_url or not self.email:
            print("Jira not configured.")
            return ""

        url = f"{self.base_url}/rest/api/3/issue"
        
        # Simple ADF paragraph for description
        adf_description = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": description or ""}]
                }
            ]
        }

        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": (summary or "")[:254],
                "description": adf_description,
                "issuetype": {"name": "Task"},
                "labels": labels
            }
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=self._get_auth_header(), json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("key", "")
            except Exception as e:
                print(f"Error creating Jira ticket: {e}")
                return ""

    async def update_ticket(self, key: str, summary: Optional[str] = None, description: Optional[str] = None) -> bool:
        if not self.base_url or not self.email:
            return False

        url = f"{self.base_url}/rest/api/3/issue/{key}"
        fields = {}
        if summary:
            fields["summary"] = summary
        if description:
             fields["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}]
                    }
                ]
            }
        
        if not fields:
            return True

        async with httpx.AsyncClient() as client:
            try:
                response = await client.put(url, headers=self._get_auth_header(), json={"fields": fields})
                response.raise_for_status()
                return True
            except Exception as e:
                print(f"Error updating Jira ticket {key}: {e}")
                return False
