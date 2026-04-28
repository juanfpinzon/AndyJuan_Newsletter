from __future__ import annotations

from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "daily-radar.yml"
README_PATH = REPOSITORY_ROOT / "README.md"


def test_daily_radar_workflow_matches_phase6_contract() -> None:
    workflow = yaml.load(
        WORKFLOW_PATH.read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    on = workflow["on"]

    assert on["workflow_dispatch"]["inputs"]["mode"]["default"] == "daily"
    assert on["workflow_dispatch"]["inputs"]["dry_run"]["default"] == "false"
    assert on["repository_dispatch"]["types"] == ["run-daily-radar"]

    job = workflow["jobs"]["run-radar"]
    assert job["env"]["OPENROUTER_API_KEY"] == "${{ secrets.OPENROUTER_API_KEY }}"
    assert job["env"]["AGENTMAIL_API_KEY"] == "${{ secrets.AGENTMAIL_API_KEY }}"
    assert job["env"]["AGENTMAIL_INBOX_ID"] == "${{ secrets.AGENTMAIL_INBOX_ID }}"
    assert job["env"]["EMAIL_FROM"] == "${{ secrets.EMAIL_FROM }}"
    assert job["env"]["NEWSDATA_API_KEY"] == "${{ secrets.NEWSDATA_API_KEY }}"

    run_script = "\n".join(
        step.get("run", "")
        for step in job["steps"]
        if isinstance(step, dict)
    )
    uses_steps = [
        step.get("uses", "")
        for step in job["steps"]
        if isinstance(step, dict)
    ]

    assert "python -m pip install --upgrade pip" in run_script
    assert 'pip install -e ".[dev]"' in run_script
    assert 'if [ -n "$DRY_RUN_FLAG" ]; then' in run_script
    assert 'python -m src.main --mode "$MODE" "$DRY_RUN_FLAG"' in run_script
    assert 'python -m src.main --mode "$MODE"' in run_script
    assert "actions/upload-artifact@v4" in uses_steps


def test_readme_documents_operations_setup() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    assert "## Operations" in readme
    assert "Mon-Fri 06:30 UTC" in readme
    assert "Sat 07:00 UTC" in readme
    assert "repository_dispatch" in readme
    assert "run-daily-radar" in readme
    assert "client_payload" in readme
    assert "/dispatches" in readme
    assert "fine-grained personal access token" in readme
    assert "Contents: write" in readme
