# jira_sync.py
import os, time, sqlite3
from hashlib import sha256
from typing import Dict, Any, List, Optional
from jira_client import JiraClient

# ---- Small local SQL helpers (match tables you created earlier) ----

def _upsert_jira_issue(conn: sqlite3.Connection, now_ts: int, key: str, issue_id: str,
                       project_key: str, summary: str, description: str,
                       status: Optional[str] = None, assignee: Optional[str] = None,
                       priority: Optional[str] = None, labels: Optional[str] = None,
                       due_date: Optional[str] = None):
    conn.execute("""
        INSERT INTO jira_issues (created_at, updated_at, jira_key, jira_id, project_key,
                                 summary, description, status, assignee, priority, labels, due_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(jira_key) DO UPDATE SET
            updated_at=excluded.updated_at,
            summary=excluded.summary,
            description=excluded.description,
            status=COALESCE(excluded.status, jira_issues.status),
            assignee=COALESCE(excluded.assignee, jira_issues.assignee),
            priority=COALESCE(excluded.priority, jira_issues.priority),
            labels=COALESCE(excluded.labels, jira_issues.labels),
            due_date=COALESCE(excluded.due_date, jira_issues.due_date)
    """, (now_ts, now_ts, key, issue_id, project_key, summary, description,
          status, assignee, priority, labels, due_date))

def _ensure_jira_tables(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jira_issues (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at INTEGER,
          updated_at INTEGER,
          jira_key TEXT UNIQUE,
          jira_id TEXT UNIQUE,
          project_key TEXT,
          summary TEXT,
          description TEXT,
          status TEXT,
          assignee TEXT,
          priority TEXT,
          labels TEXT,
          due_date TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jira_links (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at INTEGER,
          updated_at INTEGER,
          insight_id INTEGER,
          slack_message_ts TEXT,
          slack_channel_id TEXT,
          jira_key TEXT,
          UNIQUE (insight_id, jira_key)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jira_dedup (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at INTEGER,
          hash TEXT UNIQUE,
          jira_key TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jira_issues_key ON jira_issues(jira_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jira_issues_status ON jira_issues(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jira_links_ts ON jira_links(slack_message_ts)")

# ---- Public entrypoint you will call from your processing pipeline ----

def sync_jira_for_extracted_insights(conn: sqlite3.Connection,
                                     insights: Dict[str, List[Dict[str, Any]]],
                                     slack_ctx: Dict[str, Any]):
    """
    insights: dict with lists under keys like 'todos', 'facts', 'decisions'
    slack_ctx: minimal context about the source (channel_id, message_ts, etc.)
    RETURNS: list[str] -> Jira keys created in this call (e.g., ["KAN-2"])
    """
    created_keys: List[str] = []

    raw_key = os.getenv("JIRA_PROJECT_KEY", "")
    project_key = (raw_key or "").strip()
    issue_type = (os.getenv("JIRA_DEFAULT_ISSUE_TYPE", "Task") or "Task").strip()

    if not project_key:
        print("⚠️ Jira sync: JIRA_PROJECT_KEY is missing/empty. Skipping Jira create/update and mirror upsert.")
        return created_keys

    todos = (insights or {}).get("todos") or []
    if not todos:
        print("ℹ️ Jira sync: no todos in insights; nothing to sync.")
        return created_keys

    jc = JiraClient()
    now = int(time.time())
    _ensure_jira_tables(conn)

    for todo in todos:
        # Normalize summary / description
        summary = (todo.get("title") or todo.get("text") or "Untitled task").strip()
        description_lines = [
            (todo.get("text") or "").strip(),
            "",
            f"Source: {slack_ctx.get('permalink','')}",
            f"Channel: {slack_ctx.get('channel_id','')}",
            f"By: {slack_ctx.get('author','')}",
            f"When: {slack_ctx.get('ts_human','')}",
        ]
        description = "\n".join([ln for ln in description_lines if ln is not None])

        # For MVP we don't map Slack user -> Jira accountId yet.
        assignee_account_id = todo.get("assignee_account_id")  # only if you populate this later
        labels = ["ai-shadow", "from-slack"]
        due_date = (todo.get("due_date") or "")[:10] or None

        # Idempotency
        sig = f"{project_key}|{summary}|{description}|{assignee_account_id or ''}"
        h = sha256(sig.encode()).hexdigest()

        # Already created?
        row = conn.execute("SELECT jira_key FROM jira_dedup WHERE hash=?", (h,)).fetchone()
        if row:
            key = row[0]
            try:
                # 🔧 IMPORTANT: use assignee_account_id= (not assignee=)
                jc.update_issue(
                    key,
                    summary=summary,
                    description=description,
                    assignee_account_id=assignee_account_id
                )
                print(f"🔁 Jira sync: updated existing issue {key}")
            except Exception as e:
                print(f"⚠️ Jira sync: update failed for {key}: {e}")
            _upsert_jira_issue(conn, now, key, issue_id="", project_key=project_key,
                               summary=summary, description=description,
                               status=None, assignee=None,
                               priority=None, labels=",".join(labels), due_date=due_date)
            _link_if_possible(conn, now, todo, slack_ctx, key)
            continue

        # Create new issue
        try:
            created = jc.create_issue(
                project_key=project_key,
                summary=summary,
                description=description,
                issue_type=issue_type,
                assignee_account_id=assignee_account_id,   # None is fine
                labels=labels,
                due_date=due_date
            )
            key = created["key"]; issue_id = created.get("id", "")
            print(f"🆕 Jira sync: created issue {key}")
            created_keys.append(key)
        except Exception as e:
            print(f"❌ Jira sync: create failed: {e}")
            continue

        # Mirror + dedup + link
        conn.execute("INSERT INTO jira_dedup (created_at, hash, jira_key) VALUES (?, ?, ?)", (now, h, key))
        _upsert_jira_issue(conn, now, key, issue_id, project_key, summary, description,
                           status="To Do", assignee=None, priority=None,
                           labels=",".join(labels), due_date=due_date)
        _link_if_possible(conn, now, todo, slack_ctx, key)

    return created_keys



def _link_if_possible(conn: sqlite3.Connection, now_ts: int, todo: Dict[str, Any],
                      slack_ctx: Dict[str, Any], jira_key: str):
    insight_id = todo.get("insight_id")
    slack_ts = slack_ctx.get("message_ts")
    chan = slack_ctx.get("channel_id")
    if not (insight_id or (slack_ts and chan)):
        return
    conn.execute("""
        INSERT OR IGNORE INTO jira_links (created_at, updated_at, insight_id, slack_message_ts, slack_channel_id, jira_key)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (now_ts, now_ts, insight_id, slack_ts, chan, jira_key))
