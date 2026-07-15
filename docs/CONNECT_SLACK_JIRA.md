# Connect Your Slack & Jira

This guide walks you through connecting **TeamCLAW** to your own Slack workspace and optionally your Jira project. Follow the steps in order — each step builds on the previous one.

**What you will change:**

| What | Where |
|------|--------|
| Slack app (new app in your workspace) | [api.slack.com/apps](https://api.slack.com/apps) |
| Environment variables (secrets) | `.env` locally, or Render **Environment** dashboard |
| Webhook URL | Slack app → Event Subscriptions → Request URL |
| Jira API token (optional) | [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens) |

You do **not** need to modify application code unless you want to customize prompts or behavior.

---

## Step 1 — Deploy or run the server

Before configuring Slack, you need a **publicly reachable HTTPS URL** for the webhook. Slack cannot send events to `localhost`.

### Option A — Deploy to Render (recommended)

1. Fork this repo and connect it to [Render](https://render.com).
2. Render detects `render.yaml` automatically — create a new **Web Service** from the repo.
3. Set the environment variables from **Step 3** in the Render dashboard under **Environment** (mark secrets as sensitive).
4. Deploy and note your public URL, e.g. `https://your-app-name.onrender.com`.

> Render free tier may sleep after inactivity. The first request can take ~30s to wake.

### Option B — Run locally with ngrok

```bash
# Terminal 1 — run the server
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # fill in at least GROQ_API_KEY and DATABASE_URL first
uvicorn main:app --reload --port 5000

# Terminal 2 — expose it publicly
ngrok http 5000
```

Copy the `https://` URL ngrok prints (e.g. `https://abc123.ngrok-free.app`). You will need it in Step 2.

---

## Step 2 — Create and configure your Slack app

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**.
2. Name it (e.g. **TeamCLAW**) and select your workspace.

### Enable Event Subscriptions

3. Left sidebar → **Event Subscriptions** → toggle **Enable Events** on.
4. Set **Request URL** to:

   ```
   https://your-public-url/slack/events
   ```

   Replace `your-public-url` with your Render URL or ngrok URL (no trailing slash).

   Slack sends a verification challenge immediately. If your server is running and `SLACK_SIGNING_SECRET` is set (Step 3), you should see a green **Verified** checkmark.

### Subscribe to bot events

5. Under **Subscribe to bot events** → **Add Bot User Event**, add:

   | Event | Purpose |
   |-------|---------|
   | `message.channels` | Listen to public channels |
   | `message.groups` | Listen to private channels (optional) |
   | `app_mention` | Respond when `@TeamCLAW` is mentioned (recommended) |

6. Click **Save Changes**.

### Set OAuth scopes

7. Left sidebar → **OAuth & Permissions** → **Scopes** → **Bot Token Scopes**. Add:

   - `channels:history`
   - `channels:read`
   - `chat:write`
   - `groups:history` (only if you subscribed to `message.groups`)

### Install the app

8. Left sidebar → **OAuth & Permissions** → **Install to Workspace** → **Allow**.
9. Copy the **Bot User OAuth Token** (starts with `xoxb-`). Save it for Step 3.

### Get the signing secret

10. Left sidebar → **Basic Information** → **App Credentials**.
11. Copy the **Signing Secret**. Save it for Step 3.

### Invite the bot to channels

12. In Slack, open any channel you want monitored and run:

    ```
    /invite @TeamCLAW
    ```

    The bot must be a **member** of a channel to receive its messages.

---

## Step 3 — Set environment variables

Copy the template and fill in your values:

```bash
cp .env.example .env
```

### Minimum required

```env
# Groq (LLM) — free tier at https://console.groq.com
GROQ_API_KEY=your-groq-api-key

# Database — Supabase (recommended) or local PostgreSQL
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname

# Slack — from Step 2
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret
```

### Optional

```env
# Channel where TeamCLAW posts insight summaries (in addition to thread replies)
# Right-click channel in Slack → View channel details → copy ID from bottom, or from the URL
TARGET_CHANNEL_ID=C0123456789

# Alias also accepted:
# SLACK_CHANNEL_ID=C0123456789
```

> **Never commit `.env` to git.** It is listed in `.gitignore`.

### Where to set variables

| Environment | Where |
|-------------|--------|
| Local | `.env` in the repo root |
| Render | Dashboard → your service → **Environment** → add each key/value |

After changing env vars on Render, trigger a **manual redeploy** if auto-deploy is off.

### Supabase / cloud Postgres tips

- Use the **transaction pooler** URL (port `6543`) for serverless hosts like Render.
- The app auto-converts `postgres://` to `postgresql+asyncpg://` if needed.

---

## Step 4 — Connect Jira (optional)

Skip this step if you do not need automatic ticket creation.

1. Go to [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens) → **Create API token**. Copy the token.
2. Find your **Jira project key** — the prefix on ticket numbers (e.g. `ENG-42` → key is `ENG`).
3. Add to `.env` or Render **Environment**:

```env
JIRA_BASE_URL=https://your-domain.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=your-api-token
JIRA_PROJECT_KEY=ENG
```

When Jira is configured, extracted todos become Jira issues. Issue keys are posted back as Slack thread replies and linked in the insight record.

---

## Step 5 — Verify everything is connected

### Integration script

Requires a configured `.env` with real credentials:

```bash
python scripts/verify_integrations.py
```

This checks database connectivity, Groq, and runs a sample extraction workflow.

### Health endpoint

```bash
curl https://your-public-url/health
```

Expected response:

```json
{
  "status": "healthy",
  "service": "TeamCLAW",
  "config": {
    "groq": true,
    "slack": true,
    "jira": false
  }
}
```

`jira: false` is expected if you skipped Step 4. The health check confirms variables are **present**, not that Slack/Jira API calls succeed — use Step 6 for a live test.

---

## Step 6 — Send a test message

1. Invite the bot to a channel (`/invite @TeamCLAW`).
2. Send a message with a clear decision or assigned task — not a casual greeting:

   > *"We decided to use Redis for caching. @yourname please configure it by next Monday."*

Within a few seconds you should see:

- A **thread reply** in Slack with extracted insights
- The insight in the **dashboard** at `/dashboard` → **Activities**
- A **Jira ticket** (if Step 4 is configured)

If nothing happens, see [Troubleshooting](#troubleshooting) below.

---

## Troubleshooting

### Slack URL verification fails (no green checkmark)

- Confirm the server is running and reachable: `curl https://your-public-url/health`
- Set `SLACK_SIGNING_SECRET` **before** saving the Request URL (or redeploy after adding it)
- Request URL must be exactly `https://your-host/slack/events` (HTTPS, no trailing slash)

### `403 Invalid signature` on Slack events

- `SLACK_SIGNING_SECRET` in `.env` / Render must match **Basic Information → Signing Secret** in the Slack app
- Redeploy after updating the secret on Render

### Bot receives events but never replies

- **Short messages are ignored by design** (`hello`, `thanks`) — send a full sentence with a decision or task
- Bot must be **invited** to the channel
- Check server logs for `Skipping message:` (noise filter) or extraction errors
- Ensure `GROQ_API_KEY` is valid and `GROQ_MODEL` is a current model ID

### `@mention` does nothing

- Subscribe to `app_mention` in Slack app → Event Subscriptions
- Reinstall the app to the workspace after adding scopes or events

### Dashboard is empty but Slack replies work

- Insights are scoped by **tenant**. The first Slack workspace links to the default tenant automatically.
- If you migrated from an older deploy, run the SQL in the main README or set `DASHBOARD_TENANT_ID` to your workspace tenant UUID.

### Jira tickets not created

- All four vars required: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`
- Message must produce at least one **todo** in extraction (decisions alone do not create tickets)
- Confirm your Atlassian account has permission to create issues in that project

### Render cold start

- First request after idle can take 30–60s. Retry or upgrade plan for always-on.

---

## Quick reference — all environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Yes | Groq API key |
| `GROQ_MODEL` | No | Default: `llama-3.3-70b-versatile` |
| `DATABASE_URL` | Yes | PostgreSQL URL |
| `SLACK_BOT_TOKEN` | Yes | Bot token (`xoxb-...`) |
| `SLACK_SIGNING_SECRET` | Yes | Slack signing secret |
| `TARGET_CHANNEL_ID` | No | Summary channel (alias: `SLACK_CHANNEL_ID`) |
| `JIRA_BASE_URL` | No | e.g. `https://your-domain.atlassian.net` |
| `JIRA_EMAIL` | No | Atlassian account email |
| `JIRA_API_TOKEN` | No | API token from Atlassian |
| `JIRA_PROJECT_KEY` | No | e.g. `ENG` |
| `DASHBOARD_TENANT_ID` | No | Override dashboard tenant scope |
| `DEFAULT_TENANT_ID` | No | Default tenant UUID |

See [.env.example](../.env.example) for a copy-paste template.
