# AI Investment Operating System (AIOS)

AIOS is a lightweight personal investment decision-support system for AI infrastructure and HBM positions.

Version: `v0.1`

## What It Does

- Fetches market data with `yfinance`
- Retries failed market data downloads
- Falls back to a committed CSV cache when Yahoo is unavailable
- Calculates indicators and AI/HBM basket metrics
- Generates an explainable rule-based recommendation
- Produces `latest_signal.json`, `investment_dashboard.xlsx`, `dashboard.html`, `history.csv`, `execution.log`, and `deployment_summary.txt`

AIOS does not place trades and does not use API keys or secrets.

## Local Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

## Run Tests

```bash
.venv/bin/python -m pytest
```

## Run Locally

Default run:

```bash
.venv/bin/python main.py --no-input
```

Offline CSV run:

```bash
.venv/bin/python main.py \
  --config work/smoke_config.yaml \
  --portfolio work/smoke_portfolio.yaml \
  --provider csv \
  --output-dir reports \
  --no-input
```

Dry run:

```bash
.venv/bin/python main.py --dry-run --no-input
```

## Configuration

Main configuration:

```text
config.yaml
```

Portfolio configuration:

```text
portfolio.yaml
```

If `portfolio.yaml` is missing, AIOS uses safe defaults with zero positions.

## Data Fallback

The default provider is `yfinance`.

If Yahoo fails or returns no data, AIOS falls back to:

```text
data/cache/market_cache.csv
```

The dashboard displays:

- Data Source
- Last Update
- Data Quality

## Output Files

Generated files are written under:

```text
reports/
```

Local `reports/` output is ignored by Git. The GitHub Actions workflow force-adds the generated release artifacts only after tests and report generation succeed.

## GitHub Actions Deployment

Workflow:

```text
.github/workflows/aios-ci-cd.yml
```

The workflow:

1. Installs Python dependencies
2. Runs `pytest`
3. Stops if tests fail
4. Generates reports
5. Validates required report files
6. Commits generated reports
7. Deploys `dashboard.html` to GitHub Pages

No repository secrets are required.

## Required GitHub Setup

In the GitHub repository:

1. Go to `Settings -> Pages`
2. Set Source to `GitHub Actions`
3. Go to `Settings -> Actions -> General`
4. Allow workflows to read and write repository contents
5. Ensure the branch contains `.github/workflows/aios-ci-cd.yml`

## Release Check

Before release:

```bash
.venv/bin/python -m pytest
.venv/bin/python main.py --no-input
```

Confirm:

- `reports/latest_signal.json` is valid JSON
- `reports/investment_dashboard.xlsx` opens successfully
- `reports/dashboard.html` renders locally
- `reports/history.csv` has no duplicate `date,ticker` rows
- `reports/deployment_summary.txt` records execution status
