# AI Shadow Coach MVP: Knowledge Capture from Team Chats

A Slack-integrated, AI-powered assistant that automatically extracts, structures, and summarizes key decisions, action items, SOP readiness, and factual context from team conversations. Captured insights are stored in SQLite and surfaced via a lightweight web dashboard and report APIs.

## Why this project exists

- Motivation
  - Teams make important decisions in chat, but those insights get buried.
  - Manual note-taking and status reporting are inconsistent and time-consuming.
  - Leaders need a repeatable way to turn daily chatter into reliable knowledge.

- Why it was built
  - To create a low-friction, always-on “shadow coach” that listens to team chats and converts them into structured, queryable knowledge—without changing how teams already work.

- **Multi-Tenant & Scalable**
  - Built on **FastAPI** and **PostgreSQL** to handle multiple organizations (Tenants).
  - Data is strictly isolated by Tenant ID.

- The problem it solves
  - Automates extraction of decisions, todos, and facts from Slack messages.
  - Centralizes captured knowledge in a simple, queryable store.
  - Generates daily/weekly summaries and supports SOP creation readiness.

- What makes it stand out
  - Real-time extraction with a clean pipeline from Slack → LLM → storage → dashboard.
  - Practical features focused on “knowledge you can act on” (reports, SOPs, search).
  - Minimal infra: runs on a single process with SQLite; deploy-friendly (e.g., Render Free).
  - Modular design: reporting, slash commands, SOP readiness/generation, and dashboard are decoupled modules.

## Key features

- Slack integration
  - Event ingestion endpoint for messages.
  - Optional slash commands for daily/weekly reports (with date and “to here” targeting).
  - Posting summaries back to Slack channels.

- AI-powered extraction
  - Uses a Groq-backed LLM wrapper to extract:
    - Decisions
    - Todos / action items
    - Facts / noteworthy context
  - Noise filtering and heuristics to ignore low-signal messages.

- Reporting and summaries
  - SQLite-backed storage and aggregation.
  - Daily/weekly report APIs and Slack-friendly formatted outputs.
  - CSV export endpoints (for snapshots and sharing).

- SOP workflows
  - Readiness assessment: determines if a conversation is complete enough to draft an SOP.
  - SOP generation from recent channel context and user instructions.
  - REST and Slack command pathways.

- Jira Integration
  - Automatically creates Jira issues from captured "todos".
  - Syncs updates if the same task is captured again (deduplication).
  - Posts a thread reply in Slack with links to created Jira issues.

- Dashboard (no-build, static)
  - Overview tiles (reports, SOPs, summaries) and recent activities.
  - Global search across decisions/todos/facts with simple filters.
  - Role-based controls in the UI (viewer/user/admin).

- Developer-friendly
  - Simple, explicit modules for extraction, reporting, and SOP utilities.
  - Runs with a single worker; SQLite initialized automatically.
  - Optional sample Node/Express webhook server for testing.

## Architecture overview (GenAI-Native)
- **Core (`src/core/`)**: Pure business logic and interfaces. Zero external dependencies.
  - `interfaces/`: Abstract Base Classes (ABCs) for LLM, DB, Slack, Jira.
  - `models/`: Type-safe Pydantic models (`InsightRecord`, `Sop`).
  - `logic/`: Reusable business logic (`InsightExtractor`, `ReportBuilder`, `SopGenerator`, `MessageWorkflow`).

- **Adapters (`src/adapters/`)**: Concrete implementations of external tools.
  - `GroqAdapter`: Async LLM calls.
  - `SqliteAdapter`: Async DB operations using `aiosqlite`.
  - `SlackAdapter` / `JiraAdapter`: Async messaging and ticketing.

- **Infrastructure (`src/infrastructure/`)**: Wiring and Configuration.
  - `config.py`: Pydantic Settings for environment variables.
  - `container.py`: Dependency Injection container.
  - `prompts.py`: Centralized system prompts.

- **Entry Point (`main.py`)**: A thin Flask app that delegates all logic to the `Container`.

## Repository structure

- src/
  - core/
  - adapters/
  - infrastructure/
- main.py (Entry point)
- requirements.txt
- runtime.txt
- dashboard_static/ (UI assets)

## Getting started

### Prerequisites

- Python: 3.11.x (runtime.txt indicates 3.11.9)
- Slack app with:
  - Bot token
  - Signing secret
  - Event Subscriptions enabled (message events) pointing to your Flask endpoint
  - Optional slash commands for reporting and SOP workflows
- Groq API key for LLM extraction

Optional:
- Node.js for the sample webhook server (server.js) if you want to test Node-based webhooks separately.


### Configuration (environment variables)

Set the following (names reflect functionality implemented in the modules):

- Groq / LLM
  - GROQ_API_KEY

- Slack
  - SLACK_BOT_TOKEN
  - SLACK_SIGNING_SECRET
  - Optional: a target channel for posting reports/summaries (if your code supports it)

- Storage (PostgreSQL)
  - POSTGRES_USER
  - POSTGRES_PASSWORD
  - POSTGRES_DB
  - POSTGRES_HOST
  - POSTGRES_PORT

- Jira (Optional)
  - JIRA_BASE_URL (e.g., https://yourdomain.atlassian.net)
  - JIRA_EMAIL
  - JIRA_API_TOKEN
  - JIRA_PROJECT_KEY (e.g., PROJ)
  - JIRA_DEFAULT_ISSUE_TYPE (default: "Task")

- Dashboard (role-aware UI)
  - If your code is configured for token roles, set environment tokens as applicable (viewer/user/admin).
  - If you prefer a simple public dashboard, you can expose endpoints without tokens (as implemented in your codebase).

Note: Initialize and reference a single consistent INSIGHTS_DB_PATH everywhere (ingestion and APIs).

### Run locally
```bash
# Install dependencies
pip install -r requirements.txt

# Run the FastAPI app (dev mode)
uvicorn main:app --reload

# Production
uvicorn main:app --host 0.0.0.0 --port 5000 --workers 4
```
- Swagger UI (API Docs): http://localhost:5000/docs
- Dashboard: http://localhost:5000/dashboard

## Slack app setup

- Event Subscriptions
  - Enable events and point to your Flask events endpoint (e.g., /slack/events).
  - Subscribe to the message events your workflow requires.

- Slash commands (from the reporting and SOP modules)
  - Reporting examples:
    - report daily [YYYY-MM-DD]
    - report weekly [YYYY-MM-DD] [to here]
  - SOP workflows:
    - SOP readiness checks via REST/command endpoints.
    - SOP generation with in-channel triggers and REST endpoints.

- Verification
  - Ensure Slack URL verification challenges are handled by your events route.
  - Signature verification should be enabled to accept only authentic Slack requests.

## API overview (high level)

- Slack events
  - POST /slack/events
    - Handles Slack URL verification and message events.
    - Runs extraction and persists insights when applicable.

- Dashboard and report APIs
  - Auth check (if enabled): /dashboard/api/auth/me
  - Reports: /dashboard/api/reports (daily, weekly aggregations, parameters for date windows)
  - Search: /dashboard/api/search (global search over decisions/todos/facts)
  - CSV export: /dashboard/api/… (if exposed by your reporting module)
  - SOP endpoints: readiness and generation routes for programmatic access
  - Summaries and SOPs: CRUD endpoints as exposed by the modules

- Static dashboard
  - /dashboard (index.html)
  - /dashboard/static/app.js, /dashboard/static/app.css

Note: Exact query parameters and response shapes follow the implementation in reporting.py, report_commands.py, sop_readiness.py, sop_generator.py, and main.py.

## Usage guide

- In Slack
  - Invite the bot to the relevant channels.
  - Post normal messages—insightful content is automatically extracted when meaningful.
  - Use slash commands to generate daily/weekly reports and optionally post them to the current channel.

- In the dashboard
  - Open /dashboard to view overview tiles and recent activity.
  - Use Global Search to find decisions, todos, and facts.
  - Download CSV reports if supported by your build.

## Deployment

- Render-friendly setup
  - SQLite is initialized automatically; using a local file works on free tiers (ephemeral).
  - Keep a single process/worker for SQLite (e.g., gunicorn --workers 1).
  - Ensure the same INSIGHTS_DB_PATH is used by ingestion and APIs.
  - Expose /dashboard and /slack/events.

- Environment
  - Configure required environment variables (Slack, Groq, DB path).
  - If using token-based dashboard auth, add the token variables.
  - For public dashboards, use the implementation in your code to disable or relax auth accordingly.

## Troubleshooting

- AssertionError: View function mapping overwriting endpoint
  - Ensure you register the Slack events route exactly once (no duplicate decorators or endpoint names).

- Dashboard shows blank or assets 404
  - Verify index.html references /dashboard/static/app.js and /dashboard/static/app.css.
  - Ensure the Flask routes map /dashboard/static/* to the folder containing those files.

- Dashboard unauthorized (401)
  - If using role tokens, save a valid token in the dashboard Settings (or adjust backend to public mode per your implementation).
  - Confirm /dashboard/api/auth/me returns 200.

- No data in reports
  - Confirm Slack events are received (HTTP 200 to /slack/events).
  - Check logs: the ingestion step should run the LLM extraction and persist via the reporting service.
  - Verify the SQLite file path and that reads/writes use the same INSIGHTS_DB_PATH.

- SQLite concurrency or locking
  - Run a single worker process; threads are fine for read-heavy endpoints.

## Roadmap

- Additional connectors (email, docs, project trackers).
- More granular analytics and trends over time.
- Richer SOP templates and approvals.
- Pluggable persistence (e.g., Postgres) for long-term storage.
- Role-based permissions and auditability improvements.

## Contributing

- Fork the repo and create a feature branch.
- Ensure style and lint checks pass.
- Add tests or reproducible examples where applicable.
- Open a PR with a clear description and screenshots/logs for UI/backend changes.
