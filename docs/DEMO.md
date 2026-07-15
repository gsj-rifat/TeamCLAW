# TeamCLAW Demo Walkthrough

This document shows a concrete **input → output** flow for portfolio reviewers and interviewers.

## Scenario

Your team discusses a database choice in Slack:

> *"We decided to go with PostgreSQL over MongoDB. @rifat can you set up the schema by Friday?"*

## What TeamCLAW does

1. **Slack Events API** delivers the message to `POST /slack/events`.
2. **HMAC signature** is verified; the handler returns `200` immediately.
3. **Background task** runs the message pipeline:
   - Noise filter checks the message is substantive (length + LLM triage).
   - Groq (Llama 3.3 70B) extracts structured insights.
   - Insight is persisted to PostgreSQL under the workspace tenant.
   - Optional Jira issues are created for todos.
   - A thread reply is posted back to Slack.

## Structured output (example)

```json
{
  "type": "decision",
  "content": "Use PostgreSQL over MongoDB",
  "todo": {
    "assignee": "@rifat",
    "due_date": "Friday",
    "jira_issue": "ENG-42"
  },
  "source_url": "https://yourteam.slack.com/archives/C09AY2A2JTY/p..."
}
```

Stored record fields (simplified):

```json
{
  "decisions": ["Use PostgreSQL over MongoDB"],
  "todos": ["Set up database schema"],
  "facts": [],
  "message_text": "We decided to go with PostgreSQL over MongoDB. @rifat can you set up the schema by Friday?",
  "channel_id": "C09AY2A2JTY",
  "source_url": "https://yourteam.slack.com/archives/..."
}
```

## Dashboard

Open **Activities** or **Global Search** on the live dashboard to see captured insights for the tenant.

## What does *not* trigger extraction

Short or low-signal messages are intentionally skipped:

- `hello`
- `thanks`
- `@bot hello` (unless expanded into a substantive sentence)

To test, send a full sentence with a decision or assigned task.

## Interview talking points

| Question | Answer |
|----------|--------|
| How do you handle Slack's 3-second timeout? | Return 200 immediately; process in FastAPI `BackgroundTasks`. |
| How do you swap Groq for another LLM? | Implement `LLMProvider` ABC; wire a new adapter in `container.py`. |
| How is multi-tenancy enforced? | Every insight is scoped by `tenant_id`; Slack `team_id` maps to a tenant row. |
| How does the dashboard find insights? | First Slack workspace links to the default tenant; optional `DASHBOARD_TENANT_ID` override. |
