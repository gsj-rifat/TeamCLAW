# AI Shadow Coach

A Slack-integrated AI assistant that listens to team conversations, extracts structured knowledge (decisions, todos, facts), stores it in PostgreSQL, and surfaces it through a web dashboard and REST APIs. Optional Jira sync turns captured todos into tickets automatically.

**Version:** 2.0.0  
**Stack:** FastAPI · Groq LLM · PostgreSQL (Supabase) · Slack · Jira (optional)

---

## What It Does

Teams make important decisions in Slack, but that knowledge gets buried. AI Shadow Coach runs in the background as a "shadow coach":

1. **Listens** — Receives Slack message events via webhook.
2. **Filters** — Skips noise and low-signal messages.
3. **Extracts** — Uses Groq (LLM) with a "Chief of Staff" persona to pull out decisions, todos (with assignee/due date), and facts.
4. **Stores** — Persists insights in PostgreSQL with tenant isolation.
5. **Acts** — Optionally creates Jira issues and posts summaries back to Slack.
6. **Surfaces** — Dashboard and APIs for search, reports, and SOP workflows.

Every extracted insight can include a **Proof of Insight** — a permalink back to the original Slack message.

---

## Architecture

The codebase follows a GenAI-native, layered design: pure business logic in `core/`, external integrations in `adapters/`, and wiring in `infrastructure/`.

```
Slack Message
     │
     ▼
POST /slack/events  ──►  Tenant resolution (Slack team_id)
     │                          │
     ▼                          ▼
MessageWorkflow  ◄──  InsightExtractor (Groq LLM)
     │
     ├──► PostgreSQL (insights, tenants, SOPs)
     ├──► Jira (optional — create tickets from todos)
     └──► Slack (thread reply + target channel summary)

Dashboard / APIs  ◄──  ReportBuilder, SopGenerator
```

### Layer map

| Layer | Path | Responsibility |
|-------|------|----------------|
| **Core** | `src/core/` | Interfaces (ABCs), Pydantic models, pure logic |
| **Adapters** | `src/adapters/` | Groq, Postgres, Slack, Jira implementations |
| **Infrastructure** | `src/infrastructure/` | Config, DI container, DB schema, LLM prompts |
| **API** | `src/api/routes/` | FastAPI route handlers |
| **Frontend** | `dashboard_static/` | Static dashboard (HTML/CSS/JS, no build step) |
| **Entry** | `main.py` | FastAPI app, lifespan, route mounting |

### Key modules

| Module | Role |
|--------|------|
| `workflow.py` | End-to-end message pipeline: filter → extract → save → Jira → notify |
| `extraction.py` | LLM-based insight extraction and noise filtering |
| `identity.py` | Slack-first tenant auto-provisioning by `team_id` |
| `reporting.py` | Daily/weekly report generation |
| `sop.py` | SOP readiness checks and generation |
| `container.py` | Dependency injection — wires all adapters and logic |

---

## Features

### Slack integration
- Event ingestion at `POST /slack/events` with HMAC signature verification
- URL verification challenge handling
- Background processing (returns 200 immediately to Slack)
- Optional summary posts to a configured target channel
- Thread replies when Jira issues are created

### AI extraction
- Groq-backed LLM (`llama-3.3-70b-versatile` by default)
- Extracts **decisions**, **todos**, and **facts**
- Todos include **assignee** and **due date** when mentioned
- Configurable noise filter (min chars, LLM threshold)

### Multi-tenancy
- Each Slack workspace (`team_id`) maps to an isolated tenant
- Auto-provisioning on first message from a new workspace
- Default tenant UUID for single-tenant / MVP deployments
- All DB queries scoped by `tenant_id`

### Jira integration (optional)
- Creates Jira issues from extracted todos
- Includes assignee, due date, and Slack source URL in description
- Posts created issue keys as a Slack thread reply

### Dashboard & APIs
- Static dashboard at `/dashboard`
- Reports, activities, search, and SOP listing endpoints
- Swagger UI at `/docs`

### SOP workflows
- Readiness assessment before generation
- REST endpoint to generate and persist SOPs

---

## Repository structure

```
my-webhook-server/
├── main.py                      # FastAPI entry point
├── requirements.txt
├── runtime.txt                  # Python 3.11.9
├── render.yaml                  # Render.com deployment blueprint
├── Procfile                     # Legacy Heroku config
├── .env.example                 # Environment variable template
├── dashboard_static/
│   ├── index.html
│   ├── app.js
│   └── app.css
├── src/
│   ├── adapters/
│   │   ├── groq_adapter.py
│   │   ├── postgres_adapter.py
│   │   ├── slack_adapter.py
│   │   ├── jira_adapter.py
│   │   └── sqlite_adapter.py    # Legacy; not wired in container
│   ├── api/routes/
│   │   ├── slack.py
│   │   ├── reports.py
│   │   ├── sop.py
│   │   └── dashboard_api.py
│   ├── core/
│   │   ├── interfaces/          # ABCs: LLM, DB, Messaging, Tickets
│   │   ├── models/              # Pydantic data contracts
│   │   └── logic/               # Business logic
│   └── infrastructure/
│       ├── config.py
│       ├── container.py
│       ├── db_schema.py
│       └── prompts.py
└── tests/
    ├── test_smoke.py
    └── verify_integrations.py
```

---

## Prerequisites

- **Python 3.11.x** (see `runtime.txt`)
- **PostgreSQL** — local, or [Supabase](https://supabase.com) for cloud
- **Slack app** with:
  - Bot token (`xoxb-...`)
  - Signing secret
  - Event Subscriptions → `message.channels` (or relevant message events)
  - Request URL pointing to `https://your-host/slack/events`
- **Groq API key** — [console.groq.com](https://console.groq.com)

Optional:
- **Jira Cloud** account with API token for ticket sync

---

## Getting started

### 1. Clone and install

```bash
git clone https://github.com/gsj-rifat/my-webhook-server.git
cd my-webhook-server
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment

Copy the template and fill in your values:

```bash
cp .env.example .env
```

**Never commit `.env` to git.** It is listed in `.gitignore`.

### 3. Run locally

```bash
uvicorn main:app --reload --port 5000
```

| URL | Purpose |
|-----|---------|
| http://localhost:5000/ | Redirects to dashboard |
| http://localhost:5000/dashboard | Static dashboard UI |
| http://localhost:5000/docs | Swagger API docs |
| http://localhost:5000/health | Health check + config flags |

### 4. Expose for Slack (local dev)

Use [ngrok](https://ngrok.com) or similar to tunnel port 5000, then set the Slack Event Subscriptions URL to:

```
https://your-tunnel.ngrok.io/slack/events
```

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Yes | Groq API key for LLM extraction |
| `GROQ_MODEL` | No | Model ID (default: `llama-3.3-70b-versatile`) |
| `SLACK_BOT_TOKEN` | Yes* | Slack bot OAuth token |
| `SLACK_SIGNING_SECRET` | Yes* | Slack request signing secret |
| `DATABASE_URL` | Yes** | PostgreSQL connection URL (Supabase recommended) |
| `TARGET_CHANNEL_ID` | No | Slack channel ID for insight summary posts |
| `REPORT_POST_CHANNEL_ID` | No | Channel for report delivery |
| `DEFAULT_TENANT_ID` | No | UUID for single-tenant mode (default: null UUID) |
| `JIRA_BASE_URL` | No | e.g. `https://yourdomain.atlassian.net` |
| `JIRA_EMAIL` | No | Jira account email |
| `JIRA_API_TOKEN` | No | Jira API token |
| `JIRA_PROJECT_KEY` | No | Project key for auto-created issues |
| `POSTGRES_USER` | No*** | Local Postgres user (fallback if no `DATABASE_URL`) |
| `POSTGRES_PASSWORD` | No*** | Local Postgres password |
| `POSTGRES_DB` | No*** | Local Postgres database name |
| `POSTGRES_HOST` | No*** | Local Postgres host |
| `POSTGRES_PORT` | No*** | Local Postgres port |

\* Required for Slack integration to work.  
\** If unset, falls back to SQLite (`insights.db`) — suitable for quick local tests only; production should use Postgres.  
\*** Used only when `DATABASE_URL` is not set.

### Supabase / cloud Postgres

Set `DATABASE_URL` in your `.env`. The app auto-converts `postgres://` to `postgresql+asyncpg://` and disables prepared statement caching for Supabase transaction pooler compatibility.

Example (from `.env.example`):

```
DATABASE_URL=postgresql+asyncpg://postgres.your-project:password@aws-0-eu-central-1.pooler.supabase.com:5432/postgres
```

---

## API reference

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Returns `healthy` status and boolean flags for Groq, Slack, Jira config |

### Slack

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/slack/events` | Slack Events API webhook (messages, URL verification) |

### Reports

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/reports/daily?date=YYYY-MM-DD&channel_id=` | Daily insight report |
| `GET` | `/reports/weekly?start_date=YYYY-MM-DD&channel_id=` | Weekly insight report |

### SOP

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sop/generate` | Check readiness and generate an SOP (`topic`, `context[]`) |

### Dashboard API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/reports?granularity=daily&start=&end=` | Aggregated report data for dashboard |
| `GET` | `/activities?start=&end=` | Recent insight activities |
| `GET` | `/search?q=` | Global search over insights |
| `GET` | `/sops` | List stored SOPs |
| `GET` | `/summaries` | Summaries (stub — returns empty) |

All dashboard endpoints accept an optional `X-Auth-Token` header (reserved for future auth).

---

## Slack app setup

1. Create a Slack app at [api.slack.com/apps](https://api.slack.com/apps).
2. Enable **Event Subscriptions** and set Request URL to `https://your-host/slack/events`.
3. Subscribe to bot events: `message.channels` (and/or `message.groups`, `message.im` as needed).
4. Add **OAuth scopes**: `channels:history`, `chat:write`, `channels:read` (adjust for your use case).
5. Install the app to your workspace and copy the **Bot User OAuth Token**.
6. Copy the **Signing Secret** from Basic Information.
7. Invite the bot to channels you want monitored.

---

## Deployment (Render)

The repo includes `render.yaml` for [Render](https://render.com):

- **Service name:** `ai-shadow`
- **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Python:** 3.11.9

Set these secrets in the Render dashboard:

- `DATABASE_URL` (Supabase connection string)
- `GROQ_API_KEY`
- `SLACK_BOT_TOKEN`
- `SLACK_SIGNING_SECRET`
- Jira vars (if used)
- `TARGET_CHANNEL_ID` (optional)

After deploy, update your Slack app's Event Subscriptions URL to your Render service URL.

> **Note:** `Procfile` references `gunicorn` for legacy Heroku deploys. For FastAPI on Render, use the `uvicorn` start command in `render.yaml`.

---

## Database schema

Tables are created automatically on startup via `init_db()`:

| Table | Purpose |
|-------|---------|
| `tenants` | Organizations; keyed by Slack `team_id` |
| `users` | Tenant members (future auth) |
| `insights` | Extracted decisions, todos, facts (JSONB) with `source_url` |

A default tenant (`00000000-0000-0000-0000-000000000000`) is seeded on first run for single-tenant deployments.

---

## Testing

### Smoke tests

From the project root (set `PYTHONPATH` so `main` resolves):

```bash
# Windows PowerShell
$env:PYTHONPATH = "."
pytest tests/test_smoke.py -v

# macOS / Linux
PYTHONPATH=. pytest tests/test_smoke.py -v
```

Smoke tests mock the database and verify `/health`, `/docs`, and `/slack/events` routing.

### Integration verification

With a valid `.env` configured:

```bash
python tests/verify_integrations.py
```

This checks DB connectivity, Groq LLM, and end-to-end insight saving.

---

## Message processing flow

When a user posts in a monitored Slack channel:

1. **Signature verification** — HMAC-SHA256 against `SLACK_SIGNING_SECRET`.
2. **Tenant resolution** — Lookup or create tenant by Slack `team_id`.
3. **Noise filter** — Skip short or low-signal messages.
4. **LLM extraction** — Groq returns structured decisions, todos, facts.
5. **Proof of insight** — Fetch Slack permalink for the source message.
6. **Persist** — Save `InsightRecord` to PostgreSQL scoped to tenant.
7. **Jira sync** — If todos exist and Jira is configured, create issues.
8. **Notify** — Post Jira links in thread; optionally post summary to `TARGET_CHANNEL_ID`.

---

## Security

- **Do not commit `.env`** — secrets belong in environment variables or your host's secret store.
- Slack requests are verified via signing secret before processing.
- Rotate credentials immediately if they were ever exposed in git history.
- The repo ignores: `.env`, `*.db`, `__pycache__/`, `.idea/`, `mcp_config.json`.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Slack URL verification fails | Ensure `/slack/events` is reachable and returns the `challenge` value |
| 403 on Slack events | Check `SLACK_SIGNING_SECRET` matches your Slack app |
| No insights in dashboard | Confirm bot is invited to the channel; check server logs for "Skipping message" |
| DB connection errors on Supabase | Use transaction pooler URL; app sets `statement_cache_size=0` for asyncpg |
| Groq model errors | Verify `GROQ_MODEL` is a current model ID (default: `llama-3.3-70b-versatile`) |
| Dashboard blank / 404 assets | Open `/dashboard` directly; static files are served from `dashboard_static/` |
| Tests fail with `No module named 'main'` | Run pytest with `PYTHONPATH=.` from the repo root |

---

## Roadmap

- [ ] Structured logging (replace debug `print` statements)
- [ ] Dashboard auth (wire `X-Auth-Token` to roles)
- [ ] Summaries storage and retrieval
- [ ] Expanded unit test coverage
- [ ] CI pipeline (pytest on push)
- [ ] Additional connectors (email, docs, other trackers)

---

## Contributing

1. Fork the repo and create a feature branch.
2. Match existing architecture: interfaces in `core/`, implementations in `adapters/`.
3. Add or update tests for behavior changes.
4. Open a PR with a clear description.

---

## License

Private repository — all rights reserved unless otherwise specified by the owner.
