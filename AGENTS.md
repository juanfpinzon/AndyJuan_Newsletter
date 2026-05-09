# AndyJuan Personal Portfolio Radar Agent Context

## Product

Build a Python newsletter pipeline that:

- Computes direct and ETF look-through exposure
- Fetches portfolio-relevant news and macro items
- Produces a daily HTML email and a Saturday deep brief
- Labels AI-generated commentary clearly and keeps it grounded in input data

## Phase 0

Current work is limited to the repository foundation:

- package scaffolding
- logging and HTTP utilities
- LLM wrapper
- config loading
- SQLite scaffolding
- CI and workflow setup

## Constraints

- Python 3.11+
- Tests must pass locally with `pytest tests/ -v`
- CI should run `ruff check` and `pytest`
- Keep changes narrow and spec-aligned

## Available Skills

Claude should use these agent skills when needed to improve workflow and code quality:

### Planning & Design
- `agent-skills:spec-driven-development` — Create specs before coding for new features or significant changes
- `agent-skills:planning-and-task-breakdown` — Break work into ordered, verifiable tasks
- `agent-skills:idea-refine` — Refine ideas through structured thinking

### Implementation
- `agent-skills:incremental-implementation` — Build thin vertical slices, test each before expanding
- `agent-skills:context-engineering` — Load right context at the right time
- `agent-skills:source-driven-development` — Verify against official docs before implementing
- `agent-skills:frontend-ui-engineering` — Build production-quality UIs (if UI work arises)
- `agent-skills:api-and-interface-design` — Design stable interfaces with clear contracts

### Verification & Testing
- `agent-skills:test-driven-development` — Failing test first, then make it pass
- `agent-skills:debugging-and-error-recovery` — Reproduce → localize → fix → guard
- `agent-skills:browser-testing-with-devtools` — Runtime verification with Chrome DevTools

### Quality & Review
- `agent-skills:code-review-and-quality` — Five-axis review before merging
- `agent-skills:security-and-hardening` — OWASP prevention, input validation
- `agent-skills:performance-optimization` — Measure first, optimize only what matters
- `andrej-karpathy-skills:karpathy-guidelines` — Reduce common LLM coding mistakes

### Shipping & Deployment
- `agent-skills:git-workflow-and-versioning` — Atomic commits, clean history
- `agent-skills:ci-cd-and-automation` — Automated quality gates on every change
- `agent-skills:documentation-and-adrs` — Document the why, not just the what
- `agent-skills:shipping-and-launch` — Pre-launch checklist, monitoring, rollback plan

### Testing & QA Tools
- `gstack` — Fast headless browser for QA testing, site verification, dogfooding workflows
