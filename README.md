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
