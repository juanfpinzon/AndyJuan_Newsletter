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
