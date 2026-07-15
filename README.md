# TeamCLAW

> **Teams make critical decisions in Slack every day — and most of them disappear forever.**  
> TeamCLAW runs silently in the background, listening to your team's conversations and automatically extracting decisions, action items, and key facts into a searchable knowledge base.

**No manual note-taking. No missed follow-ups. No forgotten decisions.**

[![CI](https://github.com/gsj-rifat/TeamCLAW/actions/workflows/ci.yml/badge.svg)](https://github.com/gsj-rifat/TeamCLAW/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)

**Stack:** FastAPI · Groq LLM (Llama 3.3 70B) · PostgreSQL · Slack Events API · Jira (optional)

**Author:** [gsj-rifat](https://github.com/gsj-rifat)

---

## The Problem

In fast-moving teams, important decisions happen in Slack threads — sprint decisions, architecture choices, assigned tasks. But Slack is a stream, not a knowledge base. Within days, those decisions are buried and forgotten.

## What I Built

I built a production-ready AI backend that:

- **Listens** to Slack channels via webhook (no polling, no manual triggers)
- **Filters** noise using an LLM-based signal detector to skip irrelevant chatter
- **Extracts** structured insights — decisions, todos with assignees/due dates, and facts — using Groq (Llama 3.3 70B)
- **Persists** everything to PostgreSQL with multi-tenant isolation
- **Surfaces** insights through a REST API and dashboard
- **Syncs** todos to Jira when configured

I started this after watching sprint decisions get lost in Slack — I wanted to show I can design a multi-tenant backend, not just call an LLM API.

## Features

I documented the full feature set in **[docs/FEATURES.md](docs/FEATURES.md)**. Highlights:

| Area | What it does |
|:-----|:-------------|
| **Slack** | Webhook ingestion, HMAC verification, `@mentions`, thread replies |
| **Noise filter** | Ignores short/low-signal messages (e.g. `hello`, `thanks`) before calling the LLM |
| **AI extraction** | Pulls out decisions, todos (assignee + due date), and facts |
| **Storage** | PostgreSQL with tenant isolation + Slack permalink on every insight |
| **Jira** | Creates tasks from extracted todos (optional) |
| **Reports** | Daily and weekly summaries via REST API |
| **Dashboard** | Overview, Activities, Reports, Global Search, SOP Library |

Casual one-liners are filtered out by default (under 12 characters, or low confidence from the LLM). You can tune that with `NOISE_MIN_CHARS`, `NOISE_LLM_THRESHOLD`, and `NOISE_FILTER_ENABLED` — details in [FEATURES.md](docs/FEATURES.md#2-noise-filter-what-gets-ignored).

## Demo

This is the flow I tested on my own Slack workspace:

**1. Someone posts a decision in a channel**

![Sample Slack message](docs/screenshots/sample-slack-message.jpg)

**2. TeamCLAW replies in the thread with extracted insights**

![TeamCLAW thread reply](docs/screenshots/teamclaw-slack-response.jpg)

**3. The same insight shows up in the dashboard**

![TeamCLAW dashboard](docs/screenshots/teamclaw-dashboard.jpg)

A message like *"We decided to go with PostgreSQL over MongoDB. @rifat can you set up the schema by Friday?"* becomes structured data — decision, todo with assignee and due date, and a link back to the original Slack message:

```json
{
  "type": "decision",
  "content": "Use PostgreSQL over MongoDB",
  "todo": {
    "assignee": "@rifat",
    "due_date": "Friday"
  },
  "source_url": "https://yourteam.slack.com/archives/..."
}
```

Step-by-step breakdown: [docs/DEMO.md](docs/DEMO.md)

## Skills Demonstrated

| Area | What's in this project |
|:-----|:-----------------------|
| LLM / AI Engineering | Prompt engineering with structured output, noise filtering, Groq API integration |
| Backend / API | Async FastAPI, REST design, HMAC webhook verification, background tasks |
| Data & Storage | PostgreSQL with asyncpg, JSONB, multi-tenant schema design, Supabase cloud |
| System Design | Hexagonal architecture, dependency injection, interface-driven adapters |
| DevOps | Render deployment, GitHub Actions CI, environment-based config |
| Integrations | Slack Events API, Jira REST API, multi-service orchestration |

### Discussion points

| Topic | How I'd explain it |
|:------|:-------------------|
| Slack 3-second timeout | Return 200 immediately; process in FastAPI `BackgroundTasks`. |
| Swapping LLM providers | Implement `LLMProvider` ABC; wire a new adapter in `container.py`. |
| Multi-tenancy | Every DB query scoped by `tenant_id`; Slack `team_id` maps to tenant rows. |

---

## Connect Your Slack & Jira

Want to run this with your own workspace? I wrote a setup guide that walks through everything in order:

### → [docs/CONNECT_SLACK_JIRA.md](docs/CONNECT_SLACK_JIRA.md)

1. Deploy or run the server (Render or local + ngrok)
2. Create and configure your Slack app
3. Set environment variables
4. Connect Jira (optional)
5. Verify everything works
6. Send a test message

You only need to configure your Slack app and env vars — no code changes for a standard setup.

---

## Architecture & Design Decisions

I used a **ports-and-adapters (hexagonal) pattern** so business logic stays decoupled from Groq, Postgres, Slack, and Jira. Swapping any of those means writing a new adapter, not rewriting the core pipeline.

**Key decisions:**

- **Async throughout** — FastAPI + asyncpg returns 200 to Slack immediately while processing runs in the background
- **Multi-tenancy by design** — every DB query is scoped by `tenant_id` from day one
- **Interface-first** — `core/interfaces/` defines ABCs that adapters implement, which makes testing straightforward

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

| Layer | Path | Responsibility |
|:------|:-----|:---------------|
| Core | `src/core/` | Interfaces (ABCs), Pydantic models, pure logic |
| Adapters | `src/adapters/` | Groq, Postgres, Slack, Jira implementations |
| Infrastructure | `src/infrastructure/` | Config, DI container, DB schema, LLM prompts |
| API | `src/api/routes/` | FastAPI route handlers |
| Frontend | `dashboard_static/` | Static dashboard (HTML/CSS/JS, no build step) |

---

## Repository structure

```
teamclaw/
├── main.py
├── requirements.txt
├── runtime.txt
├── render.yaml
├── .env.example
├── dashboard_static/
├── docs/
│   ├── CONNECT_SLACK_JIRA.md
│   ├── FEATURES.md
│   ├── DEMO.md
│   └── screenshots/
├── scripts/
│   └── verify_integrations.py
├── src/
│   ├── adapters/
│   ├── api/routes/
│   ├── core/
│   └── infrastructure/
└── tests/
```

---

## Getting started (local development)

```bash
git clone https://github.com/gsj-rifat/teamclaw.git
cd teamclaw
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 5000
```

| URL | Purpose |
|:----|:--------|
| http://localhost:5000/dashboard | Dashboard UI |
| http://localhost:5000/docs | Swagger API docs |
| http://localhost:5000/health | Health check |

To hook up Slack locally you'll need a public tunnel — see Step 1 in [docs/CONNECT_SLACK_JIRA.md](docs/CONNECT_SLACK_JIRA.md).

---

## Environment variables

Copy [.env.example](.env.example) and fill in your keys. For where each value comes from (Slack app, Groq, Jira), see Step 3 in [docs/CONNECT_SLACK_JIRA.md](docs/CONNECT_SLACK_JIRA.md).

| Variable | Required | Description |
|:---------|:---------|:------------|
| `GROQ_API_KEY` | Yes | Groq API key |
| `DATABASE_URL` | Yes | PostgreSQL URL (`postgresql+asyncpg://...`) |
| `SLACK_BOT_TOKEN` | Yes | Slack bot OAuth token (`xoxb-...`) |
| `SLACK_SIGNING_SECRET` | Yes | Slack signing secret |
| `TARGET_CHANNEL_ID` | No | Channel for summary posts (alias: `SLACK_CHANNEL_ID`) |
| `JIRA_BASE_URL` | No | Jira Cloud URL |
| `JIRA_EMAIL` | No | Atlassian account email |
| `JIRA_API_TOKEN` | No | Atlassian API token |
| `JIRA_PROJECT_KEY` | No | Project key (e.g. `ENG`) |
| `DASHBOARD_TENANT_ID` | No | Override dashboard tenant scope |
| `DEFAULT_TENANT_ID` | No | Default tenant UUID |
| `NOISE_MIN_CHARS` | No | Min message length before LLM triage (default: `12`) |
| `NOISE_LLM_THRESHOLD` | No | Confidence cutoff for noise filter (default: `0.55`) |
| `NOISE_FILTER_ENABLED` | No | Toggle noise filter (default: `true`) |

---

## Testing

```bash
pytest tests/ -v
```

CI runs on every push via GitHub Actions. To smoke-test with real credentials:

```bash
python scripts/verify_integrations.py
```

---

## Roadmap

- [ ] SOP persistence (wire dashboard SOP Library to PostgreSQL)
- [ ] Summaries storage and retrieval
- [ ] Dashboard auth (wire `X-Auth-Token` to roles)
- [ ] Structured logging migration for remaining adapter paths
- [ ] Additional connectors (email, docs, other trackers)

---

## About

Portfolio project by [gsj-rifat](https://github.com/gsj-rifat). Feedback welcome via Issues.

## License

MIT License — see [LICENSE](LICENSE).

<!-- CV bullet: Built TeamCLAW — a production AI backend (FastAPI + Groq LLM + PostgreSQL) that monitors Slack channels, extracts structured decisions/todos using LLM prompt engineering, and syncs to Jira — featuring hexagonal architecture, multi-tenancy, and async processing. -->
