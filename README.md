# AndyJuan Personal Portfolio Radar

Personalized market-news email pipeline for Juan and Andrea. The system ranks
news by direct and ETF look-through exposure, reports daily P&L, and renders a
dark-themed HTML brief for delivery by email.

## Current Scope

This repository is being built from the spec in [docs/spec.md](docs/spec.md),
the delivery plan in [docs/plan.md](docs/plan.md), and the task breakdown in
[docs/tasks.md](docs/tasks.md).

Phase 0 establishes:

- Python package scaffolding
- Logging, HTTP, storage, and LLM utility layers
- Config loading
- CI and scheduled workflow skeletons

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest tests/ -v
```

## Operations

Phase 6 production scheduling uses GitHub `repository_dispatch` from cron-job.org
to trigger `.github/workflows/daily-radar.yml`.

The target local send times are 07:30 Mon-Fri for the daily brief and 08:00 Sat
for the deep brief. The task plan references `Mon-Fri 06:30 UTC` and
`Sat 07:00 UTC`; those UTC times only line up with CET during standard time.
To stay DST-aware year-round, set the cron-job.org job timezone to
`Europe/Madrid` (or another matching CET/CEST timezone) and schedule the local
times directly.

Recommended cron-job.org jobs:

1. Daily brief: Mon-Fri at 07:30 in `Europe/Madrid`
2. Saturday deep brief: Sat at 08:00 in `Europe/Madrid`

If you intentionally keep cron-job.org on UTC instead, use these fixed times:

1. Daily brief: Mon-Fri 06:30 UTC
2. Saturday deep brief: Sat 07:00 UTC

Use `POST https://api.github.com/repos/<owner>/<repo>/dispatches` with these
headers:

```text
Accept: application/vnd.github+json
Authorization: Bearer <GITHUB_PAT>
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json
```

Daily `repository_dispatch` body:

```json
{
  "event_type": "run-daily-radar",
  "client_payload": {
    "mode": "daily",
    "dry_run": false
  }
}
```

Saturday `repository_dispatch` body:

```json
{
  "event_type": "run-daily-radar",
  "client_payload": {
    "mode": "deep",
    "dry_run": false
  }
}
```

For a safe end-to-end smoke test, set `client_payload.dry_run` to `true` or use
manual `workflow_dispatch` with `dry_run=true` from the GitHub Actions UI.

GitHub token requirements:

- Preferred: a fine-grained personal access token scoped to the target
  repository with `Contents: write`
- Fallback: a classic personal access token with `repo` scope for a private
  repository

Required GitHub Actions secrets:

- `OPENROUTER_API_KEY`
- `AGENTMAIL_API_KEY`
- `AGENTMAIL_INBOX_ID`
- `EMAIL_FROM`
- `NEWSDATA_API_KEY`

Go-live checklist:

1. Run `workflow_dispatch` once with `mode=daily` and `dry_run=true`
2. Confirm the workflow completes and the `daily-radar-logs` artifact is present
3. Run `workflow_dispatch` again with `dry_run=false` and confirm delivery
4. Trigger each cron-job.org job from its test UI and verify the GitHub Actions
   run starts
