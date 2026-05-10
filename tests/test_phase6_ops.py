from __future__ import annotations

from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "daily-radar.yml"
CI_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
README_PATH = REPOSITORY_ROOT / "README.md"
BRANCH_PROTECTION_DOC_PATH = (
    REPOSITORY_ROOT / "docs" / "runbooks" / "github-branch-protection.md"
)


def test_daily_radar_workflow_matches_phase6_contract() -> None:
    workflow = yaml.load(
        WORKFLOW_PATH.read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    on = workflow["on"]

    assert "pull_request" not in on
    assert on["workflow_dispatch"]["inputs"]["mode"]["default"] == "daily"
    assert on["workflow_dispatch"]["inputs"]["dry_run"]["default"] == "false"
    assert on["workflow_dispatch"]["inputs"]["juan_only"]["default"] == "false"
    assert on["repository_dispatch"]["types"] == ["run-daily-radar"]

    job = workflow["jobs"]["run-radar"]
    assert job["env"]["OPENROUTER_API_KEY"] == "${{ secrets.OPENROUTER_API_KEY }}"
    assert job["env"]["AGENTMAIL_API_KEY"] == "${{ secrets.AGENTMAIL_API_KEY }}"
    assert job["env"]["AGENTMAIL_INBOX_ID"] == "${{ secrets.AGENTMAIL_INBOX_ID }}"
    assert job["env"]["EMAIL_FROM"] == "${{ secrets.EMAIL_FROM }}"
    assert job["env"]["NEWSDATA_API_KEY"] == "${{ secrets.NEWSDATA_API_KEY }}"

    config_step = next(
        step
        for step in job["steps"]
        if isinstance(step, dict) and step.get("name") == "Resolve run configuration"
    )
    assert config_step["env"]["WORKFLOW_JUAN_ONLY"] == "${{ inputs.juan_only }}"
    assert (
        config_step["env"]["DISPATCH_JUAN_ONLY"]
        == "${{ github.event.client_payload.juan_only }}"
    )

    run_step = next(
        step
        for step in job["steps"]
        if isinstance(step, dict) and step.get("name") == "Run radar pipeline"
    )
    assert (
        run_step["env"]["JUAN_ONLY_FLAG"]
        == "${{ steps.config.outputs.juan_only_flag }}"
    )

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
    assert "::error::NEWSDATA_API_KEY is not set" in run_script
    assert 'if [ -z "$DRY_RUN_FLAG" ]; then' in run_script
    assert "::error::AGENTMAIL_API_KEY is not set" in run_script
    assert 'run_args=(--mode "$MODE")' in run_script
    assert 'if [ -n "$DRY_RUN_FLAG" ]; then' in run_script
    assert 'run_args+=("$DRY_RUN_FLAG")' in run_script
    assert 'juan_only="${WORKFLOW_JUAN_ONLY:-false}"' in run_script
    assert 'DISPATCH_JUAN_ONLY' in run_script
    assert 'echo "juan_only_flag=--juan-only" >> "$GITHUB_OUTPUT"' in run_script
    assert 'run_args+=("$JUAN_ONLY_FLAG")' in run_script
    assert 'python -m src.main "${run_args[@]}"' in run_script
    assert "actions/upload-artifact@v4" in uses_steps


def test_ci_workflow_exposes_fixture_backed_digest_check() -> None:
    workflow = yaml.load(
        CI_WORKFLOW_PATH.read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    on = workflow["on"]

    assert on["pull_request"]["branches"] == ["main", "dev"]
    assert set(on["pull_request"]["types"]) == {"opened", "reopened", "synchronize"}

    jobs = workflow["jobs"]
    assert "lint-and-test" in jobs
    assert "digest-check" in jobs
    assert "run-radar" in jobs

    lint_script = "\n".join(
        step.get("run", "")
        for step in jobs["lint-and-test"]["steps"]
        if isinstance(step, dict)
    )
    assert "ruff check ." in lint_script
    assert "pytest tests/ -v" in lint_script

    digest_job = jobs["digest-check"]
    dry_run_step = next(
        step
        for step in digest_job["steps"]
        if isinstance(step, dict)
        and step.get("name") == "Run stubbed daily radar dry run"
    )
    digest_script = "\n".join(
        step.get("run", "")
        for step in digest_job["steps"]
        if isinstance(step, dict)
    )

    assert digest_job["needs"] == "lint-and-test"
    assert "tests/test_pipeline_daily.py" in digest_script
    assert "tests/test_pipeline_deep.py" in digest_script
    assert "tests/test_renderer.py" in digest_script
    assert "tests/test_run_manual.py" in digest_script
    assert "tests/test_main.py" not in digest_script
    assert "OPENROUTER_API_KEY" not in digest_script
    assert "NEWSDATA_API_KEY" not in digest_script
    assert (
        dry_run_step["env"]["ANDYJUAN_PIPELINE_STUB_CAPTURE"]
        == "${{ runner.temp }}/daily-radar-dry-run.json"
    )
    assert "python -m src.main --mode daily --dry-run" in digest_script

    run_radar_job = jobs["run-radar"]
    config_step = next(
        step
        for step in run_radar_job["steps"]
        if isinstance(step, dict)
        and step.get("name") == "Resolve run configuration"
    )
    run_radar_script = "\n".join(
        step.get("run", "")
        for step in run_radar_job["steps"]
        if isinstance(step, dict)
    )
    run_radar_step_names = [
        step.get("name")
        for step in run_radar_job["steps"]
        if isinstance(step, dict)
    ]

    assert run_radar_job["needs"] == "lint-and-test"
    assert run_radar_job["permissions"]["contents"] == "read"
    assert (
        run_radar_job["env"]["OPENROUTER_API_KEY"]
        == "${{ secrets.OPENROUTER_API_KEY }}"
    )
    assert (
        run_radar_job["env"]["AGENTMAIL_API_KEY"]
        == "${{ secrets.AGENTMAIL_API_KEY }}"
    )
    assert (
        run_radar_job["env"]["AGENTMAIL_INBOX_ID"]
        == "${{ secrets.AGENTMAIL_INBOX_ID }}"
    )
    assert run_radar_job["env"]["EMAIL_FROM"] == "${{ secrets.EMAIL_FROM }}"
    assert run_radar_job["env"]["NEWSDATA_API_KEY"] == "${{ secrets.NEWSDATA_API_KEY }}"
    assert config_step["env"]["WORKFLOW_MODE"] == "daily"
    assert config_step["env"]["WORKFLOW_JUAN_ONLY"] == "false"
    assert config_step["env"]["WORKFLOW_DRY_RUN"] == "true"
    assert "Show resolved configuration" in run_radar_step_names
    assert "Validate required secrets" in run_radar_step_names
    assert "Install dependencies" in run_radar_step_names
    assert "Run radar pipeline" in run_radar_step_names
    assert "Show pipeline log tail" in run_radar_step_names
    assert "tests/test_ci_run_radar.py" not in run_radar_script
    assert "::error::OPENROUTER_API_KEY is not set" in run_radar_script
    assert "::error::NEWSDATA_API_KEY is not set" in run_radar_script
    assert 'if [ -z "$DRY_RUN_FLAG" ]; then' in run_radar_script
    assert 'run_args=(--mode "$MODE")' in run_radar_script
    assert 'if [ -n "$DRY_RUN_FLAG" ]; then' in run_radar_script
    assert 'run_args+=("$DRY_RUN_FLAG")' in run_radar_script
    assert 'python -m src.main "${run_args[@]}"' in run_radar_script
    assert "ANDYJUAN_PIPELINE_STUB_CAPTURE" not in run_radar_script
    assert "actions/upload-artifact@v4" in [
        step.get("uses", "")
        for step in run_radar_job["steps"]
        if isinstance(step, dict)
    ]


def test_branch_protection_runbook_documents_required_checks() -> None:
    runbook = BRANCH_PROTECTION_DOC_PATH.read_text(encoding="utf-8")

    assert "main" in runbook
    assert "dev" in runbook
    assert "Require a pull request before merging" in runbook
    assert "Require status checks to pass before merging" in runbook
    assert "CI / digest-check" in runbook
    assert "CI / lint-and-test" in runbook
    assert "CI / run-radar" in runbook
    assert "fixture-backed" in runbook
    assert "same daily CLI pipeline path" in runbook
    assert "live news fetches and LLM calls" in runbook


def test_readme_documents_operations_setup() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    assert "## Operations" in readme
    assert "## Branch Protection" in readme
    assert "Mon-Fri 06:30 UTC" in readme
    assert "Sat 07:00 UTC" in readme
    assert "`main` and `dev`" in readme
    assert "repository_dispatch" in readme
    assert "run-daily-radar" in readme
    assert "client_payload" in readme
    assert "/dispatches" in readme
    assert "Dry-run still performs live news fetches and LLM calls" in readme
    assert "CI / digest-check" in readme
    assert "CI / run-radar" in readme
    assert "same daily CLI pipeline path" in readme
    assert "mode=daily" in readme
    assert "dry_run=true" in readme
    assert "fine-grained personal access token" in readme
    assert "Contents: write" in readme
