# GitHub Branch Protection for `main`

This repository uses two different GitHub Actions paths:

- `.github/workflows/ci.yml` is the pull-request validation path.
- `.github/workflows/daily-radar.yml` is the operational send path and must stay off PRs because even `dry_run=true` still performs live news and LLM calls.

Apply branch protection to `main` in the GitHub repository settings so merges are gated by CI checks instead of the operational workflow itself.

## Required Settings

Create a branch rule or ruleset targeting `main` and enable:

1. `Require a pull request before merging`
2. `Require status checks to pass before merging`
3. `Require branches to be up to date before merging`
4. `Block force pushes`
5. `Restrict deletions`
6. `Do not allow bypassing the above settings` when the repository plan supports it

## Required Status Checks

Select these checks as required:

- `CI / lint-and-test`
- `CI / digest-check`
- `CI / run-radar`

`CI / digest-check` is the branch-gating digest validation. It runs fixture-backed
pipeline and renderer tests plus a stubbed `python -m src.main --mode daily --dry-run`
smoke test, so it is safe for pull requests and does not depend on live API
secrets.

`CI / run-radar` uses the same daily CLI pipeline path as
`.github/workflows/daily-radar.yml`, but forces `mode=daily` and
`dry_run=true`. It still performs live news fetches and LLM calls, so
`OPENROUTER_API_KEY` and `NEWSDATA_API_KEY` must be available to the workflow.
The only behavior difference from the operational daily run is that email
delivery stays disabled.

## Verification

After saving the rule:

1. Open a pull request against `main`
2. Confirm GitHub shows all required checks:
   - `CI / lint-and-test`
   - `CI / digest-check`
   - `CI / run-radar`
3. Confirm direct pushes to `main` are blocked
4. Confirm `.github/workflows/daily-radar.yml` does not run for the PR
