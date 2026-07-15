# TeamCLAW

> **Teams make critical decisions in Slack every day — and most of them disappear forever.**  
> TeamCLAW runs silently in the background, listening to your team's conversations and automatically extracting decisions, action items, and key facts into a searchable knowledge base.

**No manual note-taking. No missed follow-ups. No forgotten decisions.**

[![CI](https://github.com/gsj-rifat/teamclaw/actions/workflows/ci.yml/badge.svg)](https://github.com/gsj-rifat/teamclaw/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)

**Live demo:** [ai-shadow-hiwb.onrender.com/dashboard](https://ai-shadow-hiwb.onrender.com/dashboard) · **API docs:** [/docs](https://ai-shadow-hiwb.onrender.com/docs)

> Demo may take ~30s to wake on first load (Render free tier).

**Stack:** FastAPI · Groq LLM (Llama 3.3 70B) · PostgreSQL · Slack Events API · Jira (optional)

**Author:** [gsj-rifat](https://github.com/gsj-rifat)

---

## The Problem

In fast-moving teams, important decisions happen in Slack threads — sprint decisions, architecture choices, assigned tasks. But Slack is a stream, not a knowledge base. Within days, those decisions are buried and forgotten.

## What I Built

A production-ready AI backend that:

- **Listens** to Slack channels via webhook (no polling, no manual triggers)
- **Filters** noise using an LLM-based signal detector to skip irrelevant chatter
- **Extracts** structured insights — decisions, todos with assignees/due dates, and facts — using a prompted Llama 3.3 70B model via Groq
- **Persists** everything to PostgreSQL with full multi-tenant isolation
- **Surfaces** insights through a REST API and a live dashboard
- **Syncs** todos to Jira automatically when configured

I built this after seeing decisions get lost in Slack threads during sprints — to prove I could design a multi-tenant backend, not just call an LLM API.

## Demo

See [docs/DEMO.md](docs/DEMO.md) for the full walkthrough. Add screenshots to [docs/screenshots/](docs/screenshots/).

A message like:

> *"We decided to go with PostgreSQL over MongoDB. @rifat can you set up the schema by Friday?"*

Produces this structured insight, stored and searchable within seconds:

```json
{
  "type": "decision",
  "content": "Use PostgreSQL over MongoDB",
  "todo": {
    "assignee": "@rifat",
    "due_date": "Friday",
    "jira_issue": "ENG-42"
  },
  "source_url": "https://yourteam.slack.com/archives/..."
}
```

## Skills Demonstrated

| Area | What's in this project |
|------|------------------------|
| **LLM / AI Engineering** | Prompt engineering with structured output, noise filtering, Groq API integration |
| **Backend / API** | Async FastAPI, REST design, HMAC webhook verification, background tasks |
| **Data & Storage** | PostgreSQL with asyncpg, JSONB, multi-tenant schema design, Supabase cloud |
| **System Design** | Hexagonal architecture, dependency injection, interface-driven adapters |
| **DevOps** | Render deployment, GitHub Actions CI, environment-based config |
| **Integrations** | Slack Events API, Jira REST API, multi-service orchestration |

### Interview talking points

| Question | Answer |
|----------|--------|
| Slack 3-second timeout? | Return 200 immediately; process in FastAPI `BackgroundTasks`. |
| Swap Groq for OpenAI? | Implement `LLMProvider` ABC; wire a new adapter in `container.py`. |
| Multi-tenancy? | Every DB query scoped by `tenant_id`; Slack `team_id` maps to tenant rows. |

---

## Architecture & Design Decisions

I followed a **ports-and-adapters (hexagonal) pattern** to keep business logic decoupled from external services. The LLM provider, database, and messaging platform can each be swapped by implementing a new adapter — core extraction logic stays unchanged.

**Key decisions:**

- **Async throughout** — FastAPI + asyncpg returns 200 to Slack immediately while processing runs in the background
- **Multi-tenancy by design** — every DB query is scoped by `tenant_id` from day one
- **Interface-first** — `core/interfaces/` defines ABCs that adapters implement, enabling easy mocking in tests

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
|-------|------|----------------|
| **Core** | `src/core/` | Interfaces (ABCs), Pydantic models, pure logic |
| **Adapters** | `src/adapters/` | Groq, Postgres, Slack, Jira implementations |
| **Infrastructure** | `src/infrastructure/` | Config, DI container, DB schema, LLM prompts |
| **API** | `src/api/routes/` | FastAPI route handlers |
| **Frontend** | `dashboard_static/` | Static dashboard (HTML/CSS/JS, no build step) |

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
    ├── test_smoke.py
    ├── test_extraction.py
    ├── test_noise_filter.py
    └── test_slack_signature.py
```

---

## Getting started

### Prerequisites

- Python 3.11.x (see `runtime.txt`)
- PostgreSQL — local or [Supabase](https://supabase.com)
- Slack app with bot token, signing secret, and Event Subscriptions
- Groq API key — [console.groq.com](https://console.groq.com)

### Install and run

```bash
git clone https://github.com/gsj-rifat/teamclaw.git
cd teamclaw
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in secrets — never commit .env
uvicorn main:app --reload --port 5000
```

| URL | Purpose |
|-----|---------|
| http://localhost:5000/dashboard | Dashboard UI |
| http://localhost:5000/docs | Swagger API docs |
| http://localhost:5000/health | Health check |

For local Slack testing, expose port 5000 with [ngrok](https://ngrok.com) and set the Events URL to `https://your-tunnel.ngrok.io/slack/events`.

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Yes | Groq API key |
| `DATABASE_URL` | Yes | PostgreSQL URL (`postgresql+asyncpg://...`) |
| `SLACK_BOT_TOKEN` | Yes* | Slack bot OAuth token |
| `SLACK_SIGNING_SECRET` | Yes* | Slack signing secret |
| `TARGET_CHANNEL_ID` | No | Channel for summary posts (alias: `SLACK_CHANNEL_ID`) |
| `DASHBOARD_TENANT_ID` | No | Override tenant scope for dashboard API |
| `DEFAULT_TENANT_ID` | No | Default tenant UUID |
| `JIRA_*` | No | Jira base URL, email, token, project key |

See [.env.example](.env.example) for the full template.

---

## Deployment (Render)

`render.yaml` defines a web service. Set secrets in the Render dashboard: `DATABASE_URL`, `GROQ_API_KEY`, `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, and optional Jira vars.

Slack Event Subscriptions URL:

```
https://your-render-url.onrender.com/slack/events
```

Subscribe to `message.channels` and `app_mention`.

---

## Testing

```bash
pytest tests/ -v
```

CI runs the full test suite on every push via GitHub Actions.

Manual integration check (requires real `.env`):

```bash
python scripts/verify_integrations.py
```

---

## Roadmap

- [ ] Structured logging migration for remaining adapter paths
- [ ] Dashboard auth (wire `X-Auth-Token` to roles)
- [ ] Summaries storage and retrieval
- [ ] Additional connectors (email, docs, other trackers)

---

## About This Project

Personal portfolio project by [gsj-rifat](https://github.com/gsj-rifat). Feedback welcome via Issues.

## License

MIT License — see [LICENSE](LICENSE).

<!-- CV bullet: Built TeamCLAW — a production AI backend (FastAPI + Groq LLM + PostgreSQL) that monitors Slack channels, extracts structured decisions/todos using LLM prompt engineering, and syncs to Jira — featuring hexagonal architecture, multi-tenancy, and async processing. -->
