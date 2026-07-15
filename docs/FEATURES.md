# TeamCLAW — Feature Reference

Complete overview of what TeamCLAW does, how each feature works, and what is fully implemented vs. in progress.

---

## Feature map (at a glance)

| Category | Feature | Status |
|:---------|:--------|:-------|
| Slack | Event webhook ingestion | ✅ Implemented |
| Slack | HMAC signature verification | ✅ Implemented |
| Slack | `@mention` handling | ✅ Implemented |
| Slack | Thread replies with extracted insights | ✅ Implemented |
| Slack | Optional summary posts to target channel | ✅ Implemented |
| AI | Two-stage noise filter (length + LLM) | ✅ Implemented |
| AI | Structured extraction (decisions / todos / facts) | ✅ Implemented |
| AI | Assignee & due-date extraction on todos | ✅ Implemented |
| AI | Chief-of-Staff tone normalization | ✅ Implemented |
| Storage | PostgreSQL insight persistence | ✅ Implemented |
| Storage | Proof of Insight (Slack permalink) | ✅ Implemented |
| Storage | Multi-tenant isolation by Slack workspace | ✅ Implemented |
| Jira | Auto-create issues from extracted todos | ✅ Implemented (when configured) |
| Reports | Daily report API with LLM synthesis | ✅ Implemented |
| Reports | Weekly report API with LLM synthesis | ✅ Implemented |
| Dashboard | Overview metrics | ✅ Implemented |
| Dashboard | Activities feed | ✅ Implemented |
| Dashboard | Global search (insights) | ✅ Implemented |
| Dashboard | Reports view (date range + channel filter) | ✅ Implemented |
| Dashboard | SOP Library UI | ⚠️ UI ready; DB persistence stub |
| Dashboard | Summaries archive UI | ⚠️ UI ready; API returns empty |
| SOP | Readiness check + LLM generation API | ✅ Implemented |
| SOP | Persist & list SOPs in database | 🚧 Stub |
| Auth | Dashboard `X-Auth-Token` | 🚧 Reserved for future use |

---

## 1. Slack integration

### Event ingestion

TeamCLAW receives Slack Events API callbacks at `POST /slack/events`.

| Behavior | Detail |
|:---------|:-------|
| URL verification | Responds to Slack's `challenge` during app setup |
| Signature check | Validates `X-Slack-Signature` with HMAC-SHA256 |
| Fast response | Returns `200` immediately; message processing runs in a background task |
| Event types | `message` (channel messages) and `app_mention` (`@TeamCLAW`) |
| Ignored events | Bot messages, message edits/deletes (`subtype`), unrelated event types |

### Channel monitoring

- Bot must be **invited** to a channel (`/invite @TeamCLAW`) to receive messages.
- Supports public channels (`message.channels`) and optionally private channels (`message.groups`).

### Slack responses

After a message passes the noise filter and insights are extracted:

1. **Thread reply** — formatted summary with decisions, todos (assignee + due date), facts, and a link to the original message.
2. **Target channel post** (optional) — duplicate summary to `TARGET_CHANNEL_ID` / `SLACK_CHANNEL_ID` when set and different from the source channel.
3. **Jira notification** — separate thread reply listing created issue keys when Jira is configured.
4. **Low-signal `@mention`** — if someone `@mentions` the bot with noise (e.g. "hello"), TeamCLAW replies with guidance on what to send.

---

## 2. Noise filter (what gets ignored)

TeamCLAW uses a **two-stage filter** before calling the extraction LLM. This avoids cost and clutter from casual Slack chatter.

### Stage 1 — Length gate

| Setting | Default | Env var |
|:--------|:--------|:--------|
| Minimum characters | `12` | `NOISE_MIN_CHARS` |
| Filter enabled | `true` | `NOISE_FILTER_ENABLED` |

Messages shorter than the minimum are skipped immediately (e.g. `"hello"`, `"thanks"`, `"ok"`).

### Stage 2 — LLM triage

A separate Groq prompt classifies the message and returns:

```json
{
  "is_meaningful": true,
  "category": "decision|todo|fact|update|question|process|noise",
  "confidence": 0.85,
  "reason": "Contains assigned task with deadline"
}
```

| Setting | Default | Env var |
|:--------|:--------|:--------|
| Confidence threshold | `0.55` | `NOISE_LLM_THRESHOLD` |

The message is processed only if `is_meaningful` is true **and** `confidence >= threshold`.

### Treated as noise (examples)

- Greetings, thanks, jokes, emoji-only messages
- Single-word acknowledgements (`"on it"`, `"sounds good"`)
- Vague replies with no new information
- Links or attachments without context

### Treated as signal (examples)

- Decisions and approvals
- Action items with owners or deadlines
- Status updates with specifics, blockers, or risks
- Requirements, process notes, meeting handoffs

### Fail-safe

If the noise filter LLM call errors, the message is **treated as meaningful** so nothing important is silently dropped.

---

## 3. AI insight extraction

When a message passes the noise filter, Groq (default: **Llama 3.3 70B**) extracts structured insights using a **Chief of Staff** persona.

### Output types

| Type | What is captured | Example |
|:-----|:-----------------|:--------|
| **Decisions** | Who decided what | "Engineering lead has approved migration to PostgreSQL" |
| **Todos** | Verb-first actions + assignee + due date | "Deploy hotfix" → `@Mike`, `2026-07-18` |
| **Facts** | Strategically relevant observations | "Authentication service experiencing intermittent failures since 09:00 UTC" |

### Transformation rules

- Informal language → professional business wording
- Slang converted (e.g. "server is dead" → "Server outage reported")
- Todos must start with action verbs (Deploy, Review, Investigate, …)
- Relative dates normalized to ISO format when possible

### Entity extraction on todos

The LLM looks for:

- **Assignee** — `@mentions`, "Sarah should…", "assigned to John"
- **Due date** — "by Friday", "next week", explicit dates

These appear in Slack thread replies and Jira ticket descriptions.

---

## 4. Proof of Insight

Every stored insight can include a **`source_url`** — a permanent Slack permalink to the original message.

- Retrieved via Slack `chat.getPermalink`
- Shown in thread replies as "View original message"
- Included in Jira issue descriptions as traceability

---

## 5. PostgreSQL storage & multi-tenancy

### Insight records

Each processed message creates a row with:

- `decisions`, `todos`, `facts` (JSONB lists)
- Original `message_text`, `channel_id`, Slack user ID
- `source_url`, `date`, `created_at`
- `tenant_id` for isolation

### Multi-tenancy

| Concept | Behavior |
|:--------|:---------|
| Tenant | One per Slack workspace (`team_id`) |
| Auto-provisioning | First message from a workspace creates or links a tenant |
| Dashboard scope | Queries filtered by `tenant_id` (default tenant for first workspace) |
| Override | Set `DASHBOARD_TENANT_ID` to scope the dashboard to a specific tenant |

---

## 6. Jira integration (optional)

When all Jira env vars are set and a message yields **todos**:

1. Creates a Jira **Task** per todo via REST API v3
2. Description includes todo text, assignee, due date, and Slack source URL
3. Labels: `teamclaw`, `from-slack`
4. Posts created issue keys (e.g. `ENG-42`) as a Slack thread reply

**Required env vars:** `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`

Decisions and facts alone do **not** create Jira tickets.

---

## 7. Daily & weekly reports

### REST API (LLM-synthesized)

| Endpoint | Description |
|:---------|:------------|
| `GET /reports/daily?date=YYYY-MM-DD&channel_id=` | Insights for a single day |
| `GET /reports/weekly?start_date=YYYY-MM-DD&channel_id=` | Insights for a 7-day window |

**Pipeline:**

1. Fetch insights from PostgreSQL for the date range (optionally filtered by channel)
2. Aggregate and deduplicate decisions, todos, facts
3. Groq generates a 120–180 word executive summary (`REPORT_SUMMARY_PROMPT`)
4. Falls back to bullet-list formatting if LLM fails

Returns Slack-friendly plain text (suitable for posting to a channel).

### Dashboard reports view

`GET /reports?granularity=daily&start=&end=&channel_id=` — returns aggregated counts and a summary string for the dashboard **Reports** panel (date range + optional channel filter).

---

## 8. Web dashboard

Static UI at `/dashboard` (no build step — HTML/CSS/JS).

| View | What it does | Backend |
|:-----|:-------------|:--------|
| **Overview** | Counts for reports, SOPs, summaries, activities (today + this week) | Multiple API calls |
| **Activities** | Filterable feed of captured insights by date, channel, status | `GET /activities` |
| **Reports** | Fetch report data by granularity, date range, channel | `GET /reports` |
| **Global Search** | Search insights (+ SOPs/summaries when available) by keyword, channel, date | `GET /search` |
| **SOP Library** | Browse, search, and create SOPs | `GET /sops` (list); generation via `POST /sop/generate` |
| **Summaries** | Archive and create summaries | `GET /summaries` (stub — returns empty) |
| **Settings** | Optional API token (reserved for future auth) | Local storage only |

Read-only browsing works **without** a token. Write operations may prompt for `X-Auth-Token` (auth not enforced yet).

---

## 9. Global search

`GET /search?q=&channel_id=&start=&end=`

- Searches **insights** stored for the current tenant
- Filters by date range and channel
- Keyword match on `message_text` (case-insensitive substring)
- Dashboard **Global Search** can also query SOPs and summaries in parallel when those backends are populated

Returns up to 50 results per request.

---

## 10. SOP generation

Standard Operating Procedures can be generated from conversation context.

### API

`POST /sop/generate`

```json
{
  "topic": "incident response runbook",
  "context": ["message 1", "message 2", "message 3"]
}
```

**Pipeline:**

1. **Readiness check** — requires at least 3 context strings (LLM-based readiness check planned)
2. **Generation** — Groq drafts Markdown SOP with Title, Purpose, Scope, Procedures
3. **Response** — returns `{ status: "created", id, content }` or `{ status: "incomplete", missing: [...] }`

### Dashboard SOP Library

UI supports topic entry, tags, optional channel, generate-from-context toggle, and days window. **Database list/save is currently a stub** — generated SOPs are returned by the API but not yet persisted for listing in the dashboard.

---

## 11. Summaries archive

The dashboard includes a **Summaries** view for creating and searching recap documents (title, tags, date window, generate-from-insights toggle).

**Status:** API stub — `GET /summaries` returns an empty list. UI is built; backend storage is on the [roadmap](../README.md#roadmap).

---

## 12. Security & reliability

| Feature | Detail |
|:--------|:-------|
| Slack HMAC verification | Rejects tampered webhook payloads |
| Tenant-scoped queries | Insights cannot leak across workspaces |
| Async processing | Webhook never blocks on LLM or DB latency |
| Config via env | Secrets isolated in `.env` / Render Environment |
| Health check | `GET /health` reports config presence for Groq, Slack, Jira |

---

## 13. API quick reference

| Method | Path | Purpose |
|:-------|:-----|:--------|
| `GET` | `/health` | Service health + config flags |
| `POST` | `/slack/events` | Slack Events API webhook |
| `GET` | `/reports/daily` | LLM daily report |
| `GET` | `/reports/weekly` | LLM weekly report |
| `POST` | `/sop/generate` | Generate SOP from context |
| `GET` | `/activities` | Dashboard activity feed |
| `GET` | `/search` | Global insight search |
| `GET` | `/reports` | Dashboard report aggregates |
| `GET` | `/sops` | List SOPs (empty until DB wired) |
| `GET` | `/summaries` | List summaries (stub) |
| `GET` | `/docs` | Swagger UI |

---

## 14. Configuration reference (feature-related)

| Variable | Affects |
|:---------|:--------|
| `GROQ_API_KEY` / `GROQ_MODEL` | Noise filter, extraction, reports, SOP generation |
| `NOISE_FILTER_ENABLED` | Toggle noise filter on/off |
| `NOISE_MIN_CHARS` | Minimum message length before LLM triage |
| `NOISE_LLM_THRESHOLD` | Confidence cutoff for meaningful messages |
| `TARGET_CHANNEL_ID` | Optional channel for insight summary broadcasts |
| `REPORT_POST_CHANNEL_ID` | Reserved for automated report delivery |
| `JIRA_*` | Jira ticket creation from todos |
| `DASHBOARD_TENANT_ID` | Dashboard data scope |

Full setup: [CONNECT_SLACK_JIRA.md](CONNECT_SLACK_JIRA.md)

---

## 15. Typical message lifecycle

```
Slack message posted
       │
       ▼
POST /slack/events (verify signature → 200 OK)
       │
       ▼
Background: resolve tenant from Slack team_id
       │
       ▼
Noise filter (length → LLM triage)
       │── skip ──► log reason (optional @mention reply)
       ▼
LLM extraction (decisions / todos / facts)
       │
       ├──► Save to PostgreSQL (tenant-scoped)
       ├──► Create Jira tasks (if todos + Jira configured)
       └──► Slack thread reply (+ optional target channel post)
       │
       ▼
Visible in dashboard: Activities, Search, Reports
```

---

## Related docs

- [CONNECT_SLACK_JIRA.md](CONNECT_SLACK_JIRA.md) — connect your own Slack & Jira
- [DEMO.md](DEMO.md) — example input → output walkthrough
- [screenshots/](screenshots/) — visual demo assets
