from pathlib import Path

import yaml


def test_github_actions_runs_tests_before_deployment() -> None:
    workflow_path = Path(".github/workflows/aios-ci-cd.yml")
    workflow = workflow_path.read_text(encoding="utf-8")
    parsed = yaml.load(workflow, Loader=yaml.BaseLoader)

    pytest_index = workflow.index("python -m pytest")
    generate_index = workflow.index("Generate AIOS reports")
    deploy_index = workflow.index("Deploy GitHub Pages")

    assert parsed["name"] == "AIOS CI/CD"
    assert "on" in parsed
    assert "test-generate-and-deploy" in parsed["jobs"]
    assert "[skip ci]" in parsed["jobs"]["test-generate-and-deploy"]["if"]
    assert pytest_index < generate_index < deploy_index
    assert "fetch-depth: 0" in workflow
    assert "git pull --rebase origin main" in workflow
    assert "git push origin HEAD:main" in workflow
    assert "actions/deploy-pages@v4" in workflow
    assert "reports/dashboard.html" in workflow
    assert "reports/investment_dashboard.xlsx" in workflow
    assert "reports/latest_signal.json" in workflow
    assert "reports/history.csv" in workflow
    assert "reports/execution.log" in workflow
    assert "reports/deployment_summary.txt" in workflow
    assert "secrets." not in workflow
