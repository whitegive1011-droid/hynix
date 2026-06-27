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
    assert "python main.py --provider csv --output-dir reports --no-input" in workflow
    assert "yfinance" not in workflow.lower()
    assert "stooq" not in workflow.lower()
    assert "alphavantage" not in workflow.lower()
    assert "finnhub" not in workflow.lower()
    assert "secrets." not in workflow


def test_manual_price_issue_workflow_imports_and_deploys() -> None:
    workflow_path = Path(".github/workflows/manual-price-issue.yml")
    issue_form_path = Path(".github/ISSUE_TEMPLATE/manual_prices.yml")
    workflow = workflow_path.read_text(encoding="utf-8")
    issue_form = issue_form_path.read_text(encoding="utf-8")
    parsed = yaml.load(workflow, Loader=yaml.BaseLoader)

    assert parsed["name"] == "Manual Price Issue Import"
    assert parsed["on"]["issues"]["types"] == ["opened", "edited"]
    assert parsed["permissions"]["contents"] == "write"
    assert parsed["permissions"]["issues"] == "write"
    assert parsed["permissions"]["pages"] == "write"
    assert parsed["permissions"]["id-token"] == "write"
    assert "manual-prices" in workflow
    assert "python main.py import-issue" in workflow
    assert "python main.py --provider csv --output-dir reports --no-input" in workflow
    assert "python -m pytest" in workflow
    assert "data/manual/daily_manual_prices.csv" in workflow
    assert "data/cache/market_cache.csv" in workflow
    assert "data/proxy/tradable_proxy_prices.csv" not in workflow
    assert "yfinance" not in workflow.lower()
    assert "stooq" not in workflow.lower()
    assert "alphavantage" not in workflow.lower()
    assert "finnhub" not in workflow.lower()
    assert "actions/deploy-pages@v4" in workflow
    assert "gh issue comment" in workflow
    assert "--field state=closed" in workflow
    assert "secrets." not in workflow

    assert "Manual Prices YYYY-MM-DD" in issue_form
    assert "Trading date" in issue_form
    assert "date,ticker,close,change_pct,market_cap,source,note" in issue_form
    assert "manual_upload" in issue_form
