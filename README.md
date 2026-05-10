<div align="center">

# QA Pilot

**An autonomous QA team for any web app.**

Spawn five specialist agents — Smoke · Visual · Journey · Watchdog · Aesthetic — that drive a real browser, capture evidence, and report findings like a human tester. Run it locally, in CI, in Docker, or as a service.

[Quick start](#quick-start) · [Architecture](#architecture) · [Plug into CI](#plug-into-ci) · [Self-host](#self-host) · [License: MIT](LICENSE)

</div>

---

## Why this exists

Manual QA after every deploy is the silent tax on every product team. Existing tools split the job:
Playwright handles automation but doesn't know what "looks polished" means. Vision LLMs see the page but don't drive it. CI runs scripts but doesn't write findings.

QA Pilot stitches them. Five agents, each specialized:

| Agent | Owns | Output |
|---|---|---|
| **Vega — Smoke** | "Does the app respond at all?" | Pass / fail per URL with HTTP + render check |
| **Iris — Visual** | "What does it look like at every viewport?" | Screenshots vs baselines, pixel diffs, broken-image flags |
| **Kai — Journey** | "Can a user actually do the thing?" | Per-step pass/fail with reproduction steps |
| **Argus — Watchdog** | "What's exploding in console / network?" | Bug list with stack traces and failed requests |
| **Sage — Aesthetic** | "Does this feel premium or AI-built?" | Punch list of polish items, ranked by visibility |

A **QA Lead** orchestrator dispatches them in parallel, aggregates findings into a single report, and posts it where you want it (GitHub PR comment, Slack, Telegram, Outline, JSON file).

## Quick start

```bash
# Install
pip install qa-pilot

# Set your LLM provider key (any of these — uses litellm)
export OPENAI_API_KEY=sk-...
# or ANTHROPIC_API_KEY, GEMINI_API_KEY, etc.

# Run a smoke test against any URL
qa-pilot smoke https://example.com

# Run the full team with a config file
qa-pilot run examples/cockpit.yaml

# See findings as Markdown
qa-pilot run examples/cockpit.yaml --format markdown
```

## Architecture

```
                    ┌─────────────────┐
                    │   QA Lead       │
                    │  (orchestrator) │
                    └────────┬────────┘
                             │  dispatch in parallel
       ┌─────────┬───────────┼───────────┬────────────┐
       ▼         ▼           ▼           ▼            ▼
   ┌─────┐  ┌──────┐    ┌──────┐    ┌──────┐    ┌──────┐
   │Vega │  │ Iris │    │ Kai  │    │Argus │    │ Sage │
   │smoke│  │visual│    │ flow │    │watch │    │ ux   │
   └──┬──┘  └──┬───┘    └──┬───┘    └──┬───┘    └──┬───┘
      └────────┴───────────┼───────────┴───────────┘
                           ▼
                  ┌────────────────┐
                  │  Findings[]    │  ← typed (Pydantic)
                  └────────┬───────┘
                           ▼
              ┌────────────────────────┐
              │  Reporter(s)           │
              │  • markdown / json     │
              │  • github PR comment   │
              │  • slack / telegram    │
              │  • outline / notion    │
              └────────────────────────┘
```

Each agent is an LLM-driven loop on top of **Playwright**. The browser is real.
The LLM picks the next action ("click the mic", "scroll to the orb", "screenshot the rail") based on what it sees.

LLM provider is pluggable via [litellm](https://github.com/BerriAI/litellm) — use OpenAI, Anthropic, Gemini, Groq, local Ollama, anything.

## Plug into CI

Add to your GitHub Actions:

```yaml
# .github/workflows/qa.yml
name: QA Pilot
on: [pull_request]
jobs:
  qa:
    uses: W3JDev/qa-pilot/.github/workflows/qa-reusable.yml@main
    with:
      target_url: https://staging.example.com
    secrets:
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

QA Pilot runs the team, posts findings as a PR comment, fails the check on red verdicts.

## Self-host

```bash
docker run --rm \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e TARGET_URL=https://staging.example.com \
  ghcr.io/w3jdev/qa-pilot:latest run examples/basic.yaml
```

## Configuration

A run is described by a YAML file:

```yaml
# examples/cockpit.yaml
target_url: https://w3j-cockpit-production.up.railway.app
viewports:
  - { width: 1440, height: 900, name: desktop }
  - { width: 390,  height: 844, name: mobile }
agents:
  - vega_smoke
  - iris_visual
  - sage_aesthetic
journeys:
  - name: persona-handoff-text
    steps:
      - { action: click, target: "Charlotte/Ledger persona pill" }
      - { action: type,  target: "chat input", text: "what's my cash" }
      - { action: click, target: "Send button" }
      - { action: assert, contains: "Charlotte" }
report:
  formats: [markdown, json]
  destinations:
    - { type: github_pr_comment }
    - { type: file, path: ./qa-report.md }
```

## Roadmap

- [x] Five-agent core (smoke / visual / journey / watchdog / aesthetic)
- [x] Playwright + litellm pluggable provider
- [x] CLI + Docker + GitHub Actions
- [ ] Visual regression baselines (S3-backed)
- [ ] Slack + Telegram + Outline reporters
- [ ] Hosted SaaS (qa-pilot.dev) — drop in your URL, cron, get reports
- [ ] Test-recording mode (record once, re-run forever)
- [ ] Synthetic user personas (test as 'angry user', 'first-time user', 'power user')

## License

MIT — use it however you want. Contributions welcome.

## Author

Built by [W3JDev](https://github.com/W3JDev) — part of the W3J operating stack alongside [bijou-backend](https://github.com/W3JDev/bijou-backend) and [w3j-cockpit](https://github.com/W3JDev/w3j-cockpit).
