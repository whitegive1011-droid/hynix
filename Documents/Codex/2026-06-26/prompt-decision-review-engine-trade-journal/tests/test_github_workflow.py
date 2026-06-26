from pathlib import Path


def test_github_actions_runs_tests_before_deployment() -> None:
    workflow = Path(".github/workflows/aios-ci-cd.yml").read_text(
        encoding="utf-8"
    )

    pytest_index = workflow.index("python -m pytest")
    generate_index = workflow.index("Generate AIOS reports")
    deploy_index = workflow.index("Deploy GitHub Pages")

    assert pytest_index < generate_index < deploy_index
    assert "actions/deploy-pages@v4" in workflow
    assert "reports/dashboard.html" in workflow
    assert "reports/investment_dashboard.xlsx" in workflow
    assert "reports/latest_signal.json" in workflow
    assert "reports/history.csv" in workflow
    assert "reports/execution.log" in workflow
    assert "reports/deployment_summary.txt" in workflow
    assert "secrets." not in workflow
