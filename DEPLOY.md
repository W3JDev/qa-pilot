# Deployment guide

qa-pilot ships in three runnable shapes. Pick the one that matches how
you want to use it.

| Shape | Best for | Cost |
|---|---|---|
| **Local CLI** | Pre-commit checks on your laptop | Free |
| **Docker** | Self-hosted CI runner, on-prem | Free + your infra |
| **Railway service** | Live HTTP API, on-call QA team | $5–10/mo Railway + LLM tokens |

This doc covers the Railway path because it's the most useful one — it
gives you a public URL anyone on the team (or the public, if you choose)
can hit to trigger QA runs.

## Railway — full setup (~5 minutes)

### 1. Fork or use the repo

Either:
- Use **W3JDev/qa-pilot** directly if you have access, or
- Fork it to your own GitHub account.

Railway needs to be able to read whatever repo you choose.

### 2. Create the Railway service

In your Railway dashboard:

1. **New Project** → **Deploy from GitHub repo** → pick `qa-pilot`.
2. Railway sees `railway.json` and uses `Dockerfile.server` automatically.
3. The default port is `$PORT` (Railway sets this); the Dockerfile honors it.
4. Health check path is `/health` — already configured.

### 3. Environment variables

Set these in Railway → Service → Variables:

| Variable | Required | Value | Notes |
|---|---|---|---|
| `QA_PILOT_API_TOKEN` | recommended | `<a strong random string>` | Bearer-token auth on POST routes. Without it, `/qa/*` is open. |
| `OLLAMA_API_BASE` | optional | `https://ollama-production.up.railway.app` | Points qa-pilot at your Ollama instance for free LLM calls. |
| `QA_PILOT_TEXT_MODEL` | optional | `ollama/llama3.1:8b` | Default text model for non-vision agents. Any litellm-routable string. |
| `QA_PILOT_VISION_MODEL` | optional | `ollama/llama3.2-vision:11b` | Default vision model for Iris + Sage. |
| `OPENAI_API_KEY` | optional | `sk-…` | Use OpenAI as fallback or primary. |
| `ANTHROPIC_API_KEY` | optional | `sk-ant-…` | Same — any litellm-supported provider works. |
| `GEMINI_API_KEY` | optional | `…` | Same. |
| `QA_PILOT_PUBLIC_URL` | optional | `https://qa-pilot.up.railway.app` | Used in the landing-page curl example so it's copy-pasteable. |
| `QA_PILOT_CORS_ORIGINS` | optional | `https://qa-pilot.dev,https://your-app.com` | Comma-separated. Defaults to `*`. |

### 4. First request

After deploy, find the public URL (Railway → Service → Settings → Domains, or the auto-generated `qa-pilot-production.up.railway.app`). Test it:

```bash
# Health
curl https://qa-pilot-production.up.railway.app/health

# Synchronous smoke test (returns the full Report)
curl -X POST https://qa-pilot-production.up.railway.app/qa/smoke \
  -H "Authorization: Bearer $QA_PILOT_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target_url": "https://your-app.com",
    "model": "ollama/llama3.1:8b"
  }'
```

For longer runs (full team, multiple viewports), use `/qa/run-async` and poll
`/qa/runs/{id}`:

```bash
RUN=$(curl -s -X POST .../qa/run-async \
  -H "Authorization: Bearer $QA_PILOT_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target_url": "https://your-app.com",
    "viewports": [
      {"width": 1440, "height": 900, "name": "desktop"},
      {"width": 390,  "height": 844, "name": "mobile"}
    ],
    "agents": ["vega_smoke", "iris_visual", "sage_aesthetic", "argus_watchdog"],
    "model": "ollama/llama3.1:8b"
  }' | jq -r .run_id)

# Poll
while true; do
  STATUS=$(curl -s .../qa/runs/$RUN | jq -r .status)
  echo "$STATUS"
  [ "$STATUS" = "running" ] || break
  sleep 5
done
```

## Hooking up your existing Ollama Railway instance

If you already have Ollama deployed on Railway, just point qa-pilot at it.

1. Find your Ollama service's public URL (e.g. `https://ollama-production-abcd.up.railway.app`).
2. In qa-pilot's Railway service → Variables, add:
   - `OLLAMA_API_BASE = https://ollama-production-abcd.up.railway.app`
3. Choose models — pull them on the Ollama instance first if not already there:
   - `ollama pull llama3.1:8b`         (text agents)
   - `ollama pull llama3.2-vision:11b` (vision agents — Iris + Sage)
4. Set the qa-pilot defaults:
   - `QA_PILOT_TEXT_MODEL = ollama/llama3.1:8b`
   - `QA_PILOT_VISION_MODEL = ollama/llama3.2-vision:11b`
5. Done. qa-pilot now uses your Ollama for $0/run.

If your Ollama instance is private (auth-gated), you can either expose it
publicly behind a Railway internal network alias, or proxy through a small
auth-checking middleware service. Most Ollama deployments just live behind
Railway's network and that's fine for most use cases.

## Choosing models

For best results on a budget:

| Agent kind | Recommended Ollama model | Why |
|---|---|---|
| Text-only (Vega, Argus, Kai) | `ollama/llama3.1:8b` | Fast, cheap, plenty smart for these agents |
| Vision (Iris, Sage) | `ollama/llama3.2-vision:11b` or `ollama/llava:13b` | Need real image understanding |

If you want best-in-class quality for the design critic (Sage), point that
agent at GPT-4o or Claude Sonnet 4.5 specifically — set
`QA_PILOT_VISION_MODEL=gpt-4o` or pass `--model claude-sonnet-4.5` per call.

## Cost ballpark

| Model | Per smoke run | Per full team run (3 viewports) |
|---|---|---|
| Ollama on your Railway | $0 (LLM); ~$0.001 Railway compute | ~$0.005 Railway compute |
| GPT-4o-mini | ~$0.001 | ~$0.04 |
| Claude Sonnet 4.5 | ~$0.02 | ~$0.30 |
| Gemini 2.5 Flash | ~$0.0005 | ~$0.015 |

A nightly run against 5 sites with the full team on Ollama is essentially free.

## Local development

```bash
git clone https://github.com/W3JDev/qa-pilot
cd qa-pilot
pip install -e .[server,dev]
python -m playwright install chromium

# CLI:
qa-pilot smoke https://example.com

# Or run the HTTP server locally:
uvicorn qa_pilot.server:app --reload --port 8000
```

## GitHub Actions

The workflow at `.github/workflows/qa-on-pr.yml` runs the team on every PR
and posts findings as a PR comment. Add the secrets it needs to your repo:

- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` — pick one
- `QA_PILOT_TARGET_URL` (repo variable, optional) — default URL to test

Or trigger manually with `workflow_dispatch` and pass `target_url` as input.
