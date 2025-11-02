# jira_client.py
import base64, json, os, httpx

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
        r.raise_for_status()
        return r.json()

    def create_issue(self, project_key, summary, description, issue_type="Task",
                     assignee=None, labels=None, priority=None, due_date=None):
        fields = {
            "project": {"key": project_key},
            "summary": (summary or "")[:254],
            "description": description or "",
            "issuetype": {"name": issue_type},
        }
        if assignee:
            # For Atlassian Cloud modern auth, prefer accountId. If you only have name, this may still work.
            fields["assignee"] = {"name": assignee}
        if labels:
            fields["labels"] = labels
        if priority:
            fields["priority"] = {"name": priority}
        if due_date:
            fields["duedate"] = due_date[:10]  # YYYY-MM-DD

        r = self.http.post(f"{self.base}/rest/api/3/issue",
                           headers=self.headers, data=json.dumps({"fields": fields}))
        r.raise_for_status()
        return r.json()  # { id, key, ... }

    def update_issue(self, key, summary=None, description=None, assignee=None,
                     labels=None, priority=None, due_date=None):
        fields = {}
        if summary is not None:
            fields["summary"] = summary[:254]
        if description is not None:
            fields["description"] = description
        if assignee is not None:
            fields["assignee"] = {"name": assignee}
        if labels is not None:
            fields["labels"] = labels
        if priority is not None:
            fields["priority"] = {"name": priority}
        if due_date is not None:
            fields["duedate"] = due_date[:10]
        if not fields:
            return True
        r = self.http.put(f"{self.base}/rest/api/3/issue/{key}",
                          headers=self.headers, data=json.dumps({"fields": fields}))
        r.raise_for_status()
        return True

    def get_issue(self, key):
        r = self.http.get(f"{self.base}/rest/api/3/issue/{key}", headers=self.headers)
        r.raise_for_status()
        return r.json()

    def search(self, jql, max_results=50):
        payload = {"jql": jql, "maxResults": max_results}
        r = self.http.post(f"{self.base}/rest/api/3/search",
                           headers=self.headers, data=json.dumps(payload))
        r.raise_for_status()
        return r.json()
