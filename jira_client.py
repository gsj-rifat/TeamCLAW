# jira_client.py
import base64, json, os, httpx

def _adf_paragraph(text: str) -> dict:
    """Wrap plain text into a minimal Atlassian Document Format (ADF) doc."""
    text = text or ""
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}]
            }
        ]
    }

class JiraClient:
    def __init__(self, base_url=None, email=None, api_token=None, timeout=20):
        self.base = (base_url or os.getenv("JIRA_BASE_URL", "")).rstrip("/")
        self.email = email or os.getenv("JIRA_EMAIL", "")
        self.token = api_token or os.getenv("JIRA_API_TOKEN", "")
        if not self.base or not self.email or not self.token:
            raise RuntimeError("JiraClient missing JIRA_BASE_URL, JIRA_EMAIL, or JIRA_API_TOKEN")

        auth = f"{self.email}:{self.token}".encode()
        self.headers = {
            "Authorization": "Basic " + base64.b64encode(auth).decode(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.http = httpx.Client(timeout=timeout)

    # --- basic helpers ---
    def me(self):
        r = self.http.get(f"{self.base}/rest/api/3/myself", headers=self.headers)
        self._raise_with_details(r)
        return r.json()

    def create_issue(self, project_key, summary, description, issue_type="Task",
                     assignee_account_id=None, labels=None, priority=None, due_date=None):
        """
        Create an issue. For Jira Cloud v3:
          - description should be ADF (doc format)
          - assignee must be provided as accountId (NOT name)
        """
        fields = {
            "project": {"key": project_key},
            "summary": (summary or "")[:254],
            "issuetype": {"name": issue_type},
            "description": _adf_paragraph(description or "")
        }
        if assignee_account_id:
            fields["assignee"] = {"accountId": assignee_account_id}
        if labels:
            fields["labels"] = labels
        if priority:
            fields["priority"] = {"name": priority}
        if due_date:
            fields["duedate"] = due_date[:10]  # YYYY-MM-DD

        r = self.http.post(f"{self.base}/rest/api/3/issue",
                           headers=self.headers, data=json.dumps({"fields": fields}))
        self._raise_with_details(r)
        return r.json()  # { id, key, ... }

    def update_issue(self, key, summary=None, description=None, assignee_account_id=None,
                     labels=None, priority=None, due_date=None):
        fields = {}
        if summary is not None:
            fields["summary"] = (summary or "")[:254]
        if description is not None:
            fields["description"] = _adf_paragraph(description or "")
        if assignee_account_id is not None:
            fields["assignee"] = {"accountId": assignee_account_id}
        if labels is not None:
            fields["labels"] = labels
        if priority is not None:
            fields["priority"] = {"name": priority}
        if due_date is not None:
            fields["duedate"] = (due_date or "")[:10]
        if not fields:
            return True
        r = self.http.put(f"{self.base}/rest/api/3/issue/{key}",
                          headers=self.headers, data=json.dumps({"fields": fields}))
        self._raise_with_details(r)
        return True

    def get_issue(self, key):
        r = self.http.get(f"{self.base}/rest/api/3/issue/{key}", headers=self.headers)
        self._raise_with_details(r)
        return r.json()

    def search(self, jql, max_results=50):
        payload = {"jql": jql, "maxResults": max_results}
        r = self.http.post(f"{self.base}/rest/api/3/search",
                           headers=self.headers, data=json.dumps(payload))
        self._raise_with_details(r)
        return r.json()

    # --- helpers ---
    @staticmethod
    def _raise_with_details(resp: httpx.Response):
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            # Try to include Jira error details in the exception message
            details = ""
            try:
                j = resp.json()
                msgs = j.get("errorMessages") or []
                errs = j.get("errors") or {}
                if msgs:
                    details += " errorMessages=" + repr(msgs)
                if errs:
                    details += " errors=" + repr(errs)
            except Exception:
                details = " body=" + (resp.text[:500] if resp.text else "")
            raise httpx.HTTPStatusError(
                f"{str(e)};{details}",
                request=resp.request,
                response=resp
            )
